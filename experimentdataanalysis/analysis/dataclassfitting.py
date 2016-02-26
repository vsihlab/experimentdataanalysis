# -*- coding: utf-8 -*-
"""
Created on Wed Feb 24 00:14:54 2016

@author: Michael
"""

import experimentdataanalysis.analysis.curvefitting as curvefitting
from experimentdataanalysis.analysis.generalutilities \
    import multiprocessable_map
from experimentdataanalysis.analysis.dataclasses \
    import FitData, ScanData, TimeSeries


# %%
def fit_scandata_iterable(scandata_iterable,
                          timeseriesfitfunction=None,
                          drift_fit=True,
                          multiprocessing=False):
    if not multiprocessing:
        for scandata in scandata_iterable:
            yield fit_scandata(scandata, timeseriesfitfunction, drift_fit)
    else:  # more complicated, must break down
        filepaths, scaninfos, timeserieses, _ = zip(*scandata_iterable)
        timeserieses = (get_time_offset_timeseries(timeseries)
                        for timeseries in timeserieses)
        fitoutput_iterator = multiprocessable_map(timeseriesfitfunction,
                                                  timeserieses,
                                                  multiprocessing=True)
        for filepath, scaninfo, timeseries, fitoutput in zip(
                filepaths, scaninfos, timeserieses, fitoutput_iterator):
            if drift_fit:
                newscaninfo = scaninfo.copy()  # shallow dict copy!
                newscaninfo['pre-drift_fit timeseries'] = timeseries
                yield ScanData(filepath, newscaninfo, *fitoutput)
            else:
                yield ScanData(filepath, scaninfo, timeseries, fitoutput)


# %%
def fit_scandata(scandata, timeseriesfitfunction=None, drift_fit=True):
    """
    Fits a ScanData object with the given function and returns a new
    ScanData object with a new time offset and the fitted result.
    If drift_fit is used, given function must support drift fitting
    and return (TimeSeries, FitData). Otherwise, it should just
    return FitData.
    """
    if timeseriesfitfunction is not None:
        scandata = get_time_offset_scandata(scandata)
        if drift_fit:
            timeseries = scandata.timeseries
            newscaninfo = scandata.scaninfo.copy()  # shallow dict copy!
            newscaninfo['pre-drift_fit timeseries'] = timeseries
            timeseries, fitdata = timeseriesfitfunction(timeseries)
            return ScanData(scandata.filepath,
                            newscaninfo,
                            *timeseriesfitfunction(timeseries))
        else:
            return ScanData(scandata.filepath,
                            scandata.scaninfo,
                            scandata.timeseries,
                            timeseriesfitfunction(timeseries))
    else:
        return ScanData(scandata.filepath,
                        scandata.scaninfo,
                        scandata.timeseries,
                        scandata.fitdata)


# %%
def fit_timeseries_with_one_decaying_cos(timeseries,
                                         fit_drift=True):
    """
    Takes a TimeSeries and fits as a function of a decaying cosine
    with variable phase, plus a sharp exponential and a flat offset
    using fit_timeseries__drift_fitting(timeseries, fitfunction)

    if fit_drift is False:
        returns FitData(timeseries)
    if fit_drift is True:
        returns (no_bkgd_timeseries, FitData(timeseries))
            where no_bkgd_timeseries is timeseries with background
            drift subtracted out.
    """
    if fit_drift:
        return fit_timeseries_plus_drift_fitting(
                timeseries,
                curvefitting.fit_sorted_series_to_decaying_cos)
    else:
        return curvefitting.fit_sorted_series_to_decaying_cos(timeseries)


def fit_timeseries_with_two_decaying_cos(timeseries,
                                         fit_drift=True):
    """
    Takes a TimeSeries and fits as a function of two decaying cosines,
    plus a sharp exponential and a flat offset using
    fit_timeseries_plus_drift_fitting(timeseries, fitfunction)

    if fit_drift is False:
        returns FitData(timeseries)
    if fit_drift is True:
        returns (no_bkgd_timeseries, FitData(timeseries))
            where no_bkgd_timeseries is timeseries with background
            drift subtracted out.
    """
    if fit_drift:
        return fit_timeseries_plus_drift_fitting(
                timeseries,
                curvefitting.fit_sorted_series_to_two_decaying_cos)
    else:
        return curvefitting.fit_sorted_series_to_two_decaying_cos(timeseries)


# %%
def fit_timeseries_plus_drift_fitting(timeseries, fitfunction):
    """
    Takes a TimeSeries and fits as a function of two decaying cosines,
    plus a sharp exponential and a flat offset.

    After the first fit attempt, fits a 5th order polynomial to the
    background, subtracts the polynomial, then repeats. The third fit
    (after two background correction steps) is returned, along with
    a background-corrected version of the TimeSeries input.

    Return format: (TimeSeries time_offset_background_corrected_data,
                        FitData fit_results)

    Positional arguments:
    timeseries -- TimeSeries object containing data to fit.
    function (TimeSeries->FitData): function mapping timeseries to FitData
    """
    # "timeseries" needs to be a container object, not a pure iterator,
    # since we need to iterate over it several times
    if iter(timeseries) is iter(timeseries):  # if pure iterator
        raise TypeError("fit_timeseries_plus_drift_fitting: timeseries " +
                        "must be a container object, not an iterator.")

    firstfit = fitfunction(timeseries)
    data_bkgd = timeseries - firstfit.fittimeseries

    firstbkgdfit = curvefitting.fit_unsorted_series_to_polynomial(data_bkgd, 5)
    data_minusbkgd = timeseries - firstbkgdfit.fittimeseries

    secondfit = fitfunction(data_minusbkgd)
    data_bkgd2 = timeseries - secondfit.fittimeseries

    secondbkgdfit = \
        curvefitting.fit_unsorted_series_to_polynomial(data_bkgd2, 5)
    data_minusbkgd2 = timeseries - secondbkgdfit.fittimeseries

    thirdfit = fitfunction(data_minusbkgd2)

    time_offset_no_bkgd_data = data_minusbkgd2
    final_fit = thirdfit
    return time_offset_no_bkgd_data, final_fit


# %%
def get_time_offset_scandata(scandata):
    oldtimeseries = scandata.timeseries
    newscaninfo = scandata.scaninfo.copy()  # shallow dict copy!
    newscaninfo['pre-time_offset timeseries'] = oldtimeseries
    return ScanData(scandata.filepath,
                    newscaninfo,
                    get_time_offset_timeseries(oldtimeseries),
                    scandata.fitdata)


def get_time_offset_timeseries(timeseries):
    time_at_datamax, datamax = curvefitting.get_max_value_data_pt(timeseries)
    excluded_times = [time for time, value in timeseries.datatuples()
                      if abs(value) >= datamax/2]
    # insert sanity check if too many times excluded?
    if len(excluded_times) > len(timeseries)/10:
        excluded_times = [0]
    time_offset = max(excluded_times)
    exclusion_start = min(excluded_times) - time_offset
    return TimeSeries(((time - time_offset, value)
                       for time, value in
                       timeseries.datatuples(unsorted=True)),
                      excluded_intervals=[(exclusion_start, 0)])
