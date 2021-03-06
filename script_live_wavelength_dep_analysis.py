# -*- coding: utf-8 -*-
"""
Created on Tue Jan 31 13:32:15 2017

@author: Michael
"""

import matplotlib.pyplot as plt
import numpy as np
import scipy.ndimage.filters as filters
import scipy.stats as stats

from experimentdataanalysis.analysis.dataclasses import ScanData
from experimentdataanalysis.analysis.scandataprocessing \
    import make_scandata_time_delay_positive, \
           make_scandata_phase_continuous, \
           gaussian_smooth_scandata, \
           process_scandata_fields, \
           scandata_model_fit
from experimentdataanalysis.analysis.featurevectors import \
    scandata_list_to_fvec_scandata, \
    split_fvec_scandata_by_training_and_test
from experimentdataanalysis.analysis.scandatasetprocessing \
    import sort_scandata_into_sets, fit_scandataset_list_to_model
from experimentdataanalysis.parsing.scandataparsing import \
        fetch_dir_as_unfit_scandata_iterator

import fit_models_two_species_pump_probe as two_species_model


#GFACTORCONSTANT = 0.013996  # 1/(ps*Tesla), = bohr magneton/2*pi*hbar
GFACTORCONSTANT = 1.3996e-5  # 1/(ps*mTesla), = bohr magneton/2*pi*hbar
LASER_REPRATE = 13160  # ps period

# FILENAME-TO-INFO-DICT PARSING RULES
# 1. If first string found, register second string as
#    tag containing third string/value
#        e.g. if keyword_list contains ("warmup", "Warmup?", True):
#             "...warmup..." -> {"Warmup?": True}
this_element_keyword_list = [("TRKR", "IsTRKR?", True),
                             ("RSA", "IsRSA?", True)]

# 2. If string in element[0] is found in filepath separated from other
#    characters by '_'s, will record adjacent number and store in
#    scandata's info dict under the key element[1], as a float
#    if possible.
#    e.g. TRKR_15Vcm_230mT.dat -> {"Electric Field (V/cm)": 15.0,
#                                  "Magnetic Field (mT)": 230.0}
filepath_element_keyword_list = [("Vcm", "Electric Field (V/cm)"),
                                 ("mT", "Magnetic Field (mT)"),
                                 ("K", "Set Temperature (K)"),
                                 ("nm", "Wavelength (nm)"),
                                 ("ps", "Delay Time (ps)"),
                                 ("run", "RunIndex"),
                                 ("V", "Voltage (V)"),
                                 ("x", "SecondScanCoord")]

# for this one, if element [0] is found,
# next element stored w/ key given by elements [1][0], [1][1], [1][2], etc.
filepath_next_element_keyword_list = [("Ind", "FirstScanIndex"),
                                      ("2Dscan", ["SecondScanType",
                                                  "FirstScanType"]),
                                      ("Voltage", "Voltage (V)"),
                                      ("MirrorZ", "Pump-Probe Distance (um)")]
FILEPATH_PARSING_KEYWORD_LISTS = [this_element_keyword_list,
                                  filepath_next_element_keyword_list,
                                  filepath_element_keyword_list]


# HELPER FUNCTIONS
def plot_scandata(scandata, yfield=None, model=None,
                  label="", fmt="-bd", fit_fmt="xr-"):
    if yfield is None:
        yfield = scandata.yfield
    x_vals, y_vals, y_errs = scandata.get_field_xyyerr(yfield)
    if y_errs is not None:
        plt.errorbar(x_vals, y_vals, yerr=y_errs, label=label, fmt=fmt)
    else:
        plt.plot(x_vals, y_vals, fmt, label=label)
    if scandata.get_field_fitdata(yfield) is not None:
        y_vals = scandata.get_field_fitdata(yfield).fityvals
        if model is not None:
            x_vals = np.linspace(min(x_vals), max(x_vals), 1000)
            params = scandata.get_field_fitdata(yfield).fitparams
            y_vals = model.fitfunction(x_vals, *params)
        plt.plot(x_vals, y_vals, fit_fmt)


# %%
if __name__ == '__main__':
# %%
    # DATA TO FIT
#    dirpath = ("C:\\Data\\fake_data\\" +
#               "fake_trkr")
#               "fake_trkr_huge_slopes")
#               "fake_rsa")
#    dirpath = ("C:\\Data\\august_data\\160902\\" +
#               "WavelengthDependence_TRKRvsB")
#               "BestDataFromWavelengthDependence_TRKRvsV_300mT_" +
#                   "033XT-A5_818.9nm_30K_2Dscan_Voltage_DelayTime")
#               "LowV_818.0nm_WavelengthDependence_TRKRvsV_200mT")
#    dirpath = ("C:\\Data\\173117\\" +
#               "Voltage_3_TRKRvsPumpPosition___818.6nm_30K_2Dscan_MirrorZ_DelayTime")
    dirpath = ("C:\\Data\\feb2017_data\\" +
               "lookingforDNP")

    print("---")
    print("PROCESSING LOG:")
    print("Examining directory:\n{}".format(dirpath))

    # DATA OPTIONS:
    # manipulations on each scandata, e.g. filling missing info:
    def update_scandata_info(scandata):
        try:
            second_scan_key = scandata.info['SecondScanType']
            second_scan_value = scandata.info['SecondScanCoord']
            scandata.info[second_scan_key] = second_scan_value
        except KeyError:
            pass
        if ('IsTRKR?', True) in scandata.info.items() and \
                ('IsRSA?', True) not in scandata.info.items():
            scandata.info['IsRSA?'] = False
            scandata.info['TRKRorRSA?'] = "TRKR"
        elif ('IsRSA?', True) in scandata.info.items() and \
                ('IsTRKR?', True) not in scandata.info.items():
            scandata.info['IsTRKR?'] = False
            scandata.info['TRKRorRSA?'] = "RSA"
        else:
            scandata.info['IsTRKR?'] = False
            scandata.info['IsRSA?'] = False
            scandata.info['TRKRorRSA?'] = "Unknown"
        if 'Set Temperature (K)' not in scandata.info.keys():
            scandata.info['Set Temperature (K)'] = 30.0  # ASSUME DEFAULT
        if 'temperature' not in scandata.fields:
            scandata.info['temperature'] = scandata.info['Set Temperature (K)']
        if 'Electric Field (V/cm)' not in scandata.info:
            if 'Voltage (V)' in scandata.info:
                efield = 20 * scandata.info['Voltage (V)']
                scandata.info['Electric Field (V/cm)'] = efield
            else:
                scandata.info['Electric Field (V/cm)'] = 0.0
        if 'Pump-Probe Distance (um)' not in scandata.info.keys():
            scandata.info['Pump-Probe Distance (um)'] = 0.0
    # NOTE: must be manually written based on choices above:
    print("ScanData info updates to apply:")
    print("  -Set 'IsTRKR?', 'IsRSA?', 'TRKRorRSA' flags " +
          "based on 'TRKR' or 'RSA' in filename/header")
    print("  -Assume 30K set temp if not given")
    print("  -Assume set temp is actual temp if not measured")
    print("  -Set electric field (V/cm) to be applied voltage * 20")
    print("  -Other misc. assumptions of 'value = 0' when value not found")

    # DEFINE SCANDATASETS
    scandataset_sort_keys = [
                             "TRKRorRSA?",
                             "Wavelength (nm)",
#                             "Voltage (V)",
                            ]
    # updating each ScanDataSet's model
    def update_scandataset_model(scandataset):
        set_model = scandataset.model
        set_model_params = set_model.model_params

        # SET MODEL PUMP-PROBE DIST
        set_pump_probe_dist = \
            scandataset.scandata_list[0].info.get('Pump-Probe Distance (um)')
        if set_pump_probe_dist is not None:
            pump_probe_dist_config = {'free': False,
                                      'initial value': set_pump_probe_dist}
        set_model_params['pump_probe_dist'] = pump_probe_dist_config

        # SET MODEL ESTIMATED DRIFT VELOCITY
        set_efield = \
            scandataset.scandata_list[0].info.get('Electric Field (V/cm)')
        if set_efield is not None:
            est_mobility = 1e-4
            est_drift_velocity = est_mobility * set_efield
            drift_velocity_config = {'free': False,
                                     'initial value': est_drift_velocity,
                                     'bounds': (0.8 * est_drift_velocity,
                                                1.2 * est_drift_velocity)}
        set_model_params['drift_velocity1'] = drift_velocity_config.copy()
        set_model_params['drift_velocity2'] = drift_velocity_config.copy()
    print("Sorting ScanData into ScanDataSets grouped by {}".format(
            ", ".join(scandataset_sort_keys)))
    print("ScanDataSet model updates to apply:")
    print("  -Set initial value for drift velocity for both species at " +
          "1e-4 * electric field")
    print("  -Fix pump-probe-distance ")

    # manually set uncertainty of data
    fixed_uncertainty = 2e-4
#    fixed_uncertainty = None  # ...or don't. set model's ignore_weights to True
    print("Fixing y-value uncertainty at '{}'".format(fixed_uncertainty))

    # excluded intervals of data's xfield (assumed scan coordinate)
    # (replaces model-specific excluded intervals)
    # (remember, applied post-data-filters, e.g. forcing positive delay times)
    excluded_intervals = [
#                          [-40, 300],
#                          [LASER_REPRATE - 15, 15000]]  # neg data on to 15ps
                          [7000, 15000]]  # no negative data at all
    print("Excluding X-intervals: {}".format(excluded_intervals))

#    timefield = 'Delay Time (ps)'  # RSA DATA
#    bfieldfield = 'scancoord'  # RSA DATA
    timefield = 'scancoord'  # TRKR DATA
    yfield = 'lockin1x'
    print("Y-value of data given by field: {}".format(yfield))

    # DEFINE MODEL
#    model = two_species_model.TwoSpeciesTwoGFactorsTRKRModel()
    model = two_species_model.get_two_species_TRKR_model()
    # vain attempt to fix multiprocessing:
#    model.fitfunction = two_species_model.fitfcn_two_species_exp_sin_decay_TRKR
    print("Using model: {}".format(model.model_name))
    model.excluded_intervals = excluded_intervals
#    model.ignore_weights = True
#    params = feature_vector_model_1.model_params  # simplify handle
#    params['lifetime1'] = {'free': True,
#                           'initial value': 20000,
#                           'bounds': (0, np.inf)}
#    params['lifetime2'] = {'free': True,
#                           'initial value': 8000,
#                           'bounds': (0, np.inf)}
 
# %%
    # FETCH DATA
    scandata_list = \
        list(fetch_dir_as_unfit_scandata_iterator(
                    directorypath=dirpath,
                    yfield=yfield,
                    yfield_error_val=fixed_uncertainty,
                    parsing_keywordlists=FILEPATH_PARSING_KEYWORD_LISTS))
    print("Extracted {} ScanData from dir path".format(len(scandata_list)))

    # APPLY CORRECTIONS/FILTERS TO DATA
    for scandata in scandata_list:
        update_scandata_info(scandata)
        if scandata.info['IsTRKR?'] is True:
#            gaussian_smooth_scandata(scandata,
#                                     fields_to_process=[yfield],
#                                     gaussian_width=600,
#                                     edge_handling='reflect',
#                                     subtract_smoothed_data_from_original=True)
            make_scandata_time_delay_positive(scandata,
                                              zero_delay_offset=-15,
                                              neg_time_weight_multiplier=5.0)
    print("Applied earlier-defined ScanData info updates.")
    print("Applied ScanData filters: " +
          "gaussian smoothing, pos-definite time delays")

# %%
#    # poke around at scandata:
#    scandata_ind_to_examine = 0
#    scandata_to_examine  = scandata_list[scandata_ind_to_examine]
#    print('Extracted info from ScanData #{}'.format(scandata_ind_to_examine))
#    for key, value in scandata_to_examine.info.items():
#        print("{}: {}".format(key, value))
#    plt.plot(*scandata_to_examine.xy)


# %%
    # SORT INTO SCANDATASETS
    scandataset_list = sort_scandata_into_sets(scandata_list, model,
                                               scandataset_sort_keys)
    print("Sorted ScanData into {} ScanDataSets grouped by {}".format(
            len(scandataset_list), ", ".join(scandataset_sort_keys)))

    # APPLY CHANGES TO EACH SCANDATASET'S MODEL
    for scandataset in scandataset_list:
        update_scandataset_model(scandataset)
    print("Applied earlier-defined ScanDataSet model updates.")
    print("Applied ScanDataSet-specific filters:")
    print("  -[none]")


# %%
#    # poke around at data in scandatasets:
#    scandata_set_ind = 0
#    scandata_ind_to_examine = 0
#    scandata_to_examine = \
#        scandataset_list[scandata_set_ind].scandata_list[scandata_ind_to_examine]
#    print('Extracted info from ScanData #{}'.format(scandata_ind_to_examine))
#    for key, value in scandata_to_examine.info.items():
#        print("{}: {}".format(key, value))
#    plt.plot(*scandata_to_examine.xy)
    

# %%
    # FIT DATA
# TODO: FIX MULTIPROCESSING
#    for scandataset in scandataset_list:
#        scandataset.fit_scandata_to_model(multiprocessing=True)
    fit_scandataset_list_to_model(scandataset_list, multiprocessing=False)


# %%
if False:
# %% PLOT FIT SCANDATASETS _OR_ PLOT CUSTOM FIT
    # For each figure to plot, list the scandatasets and scandata to plot
    # (if value is 'all', plot all!)
#    figure_list = [{'scandatasets': [scandataset],  # just one set per figure
#                    'scandata_indices_each_set': ['all'],
#                    'title': str(scandataset.setname) + 'nm, @10K',
#                    'ignore_fit': False,
#                    'forced_fitparams': None}
#                   for scandataset in scandataset_list
#                   if 'TRKR' in scandataset.setname]

    figure_list = [{'scandatasets': scandataset_list[:3],
                    'scandata_indices_each_set': ['all', 'all', 'all'],
                    'title': str(scandataset.setname) + '@10K',
                    'ignore_fit': False,
                    'forced_fitparams': None},
                    {'scandatasets': scandataset_list[3:],
                    'scandata_indices_each_set': ['all', 'all', 'all'],
                    'title': str(scandataset.setname) + '@10K',
                    'ignore_fit': False,
                    'forced_fitparams': None}]

    for figure_dict in figure_list:
        plot_scandata_list = []
        plot_model_list = []
        fig_scandataset_list = figure_dict['scandatasets']
        if fig_scandataset_list == ['all']:
            fig_scandataset_list = scandataset_list.copy()
        for set_ind, current_scandataset in enumerate(fig_scandataset_list):
            current_model = current_scandataset.model
            scandata_indices = figure_dict['scandata_indices_each_set'][set_ind]
            if scandata_indices is 'all':
                scandata_indices = np.arange(len(current_scandataset.scandata_list))
            for scandata_ind in scandata_indices:
                current_scandata = current_scandataset.scandata_list[scandata_ind]
                plot_scandata_list.append(current_scandata)
                plot_model_list.append(current_model)
    
        plt.figure()
        for plot_ind, (current_scandata, current_model) in \
                            enumerate(zip(plot_scandata_list, plot_model_list)):
            # GET TITLE FOR EACH PLOT
            title_items = []
#            if 'Wavelength (nm)' in current_scandata.info.keys():
#                current_wavelength = current_scandata.info['Wavelength (nm)']
#                title_items.append("Wavelength: {} nm".format(current_wavelength))
#            if 'temperature' in current_scandata.fields:
#                current_temp = np.mean(current_scandata.temperature)
#                title_items.append("Temp: {:.1f} K".format(current_temp))
#            elif 'Set Temperature (K)' in current_scandata.info.keys():
#                current_temp = current_scandata.info['Set Temperature (K)']
#                title_items.append("Temp: {:.1f} K".format(current_temp))
#            if 'Electric Field (V/cm)' in current_scandata.info.keys():
#                current_efield = current_scandata.info['Electric Field (V/cm)']
#                title_items.append("E-Field: {} V/cm".format(current_efield))
            if 'Magnetic Field (mT)' in current_scandata.info.keys():
                current_bfield = current_scandata.info['Magnetic Field (mT)']
                title_items.append("B-Field: {} mT".format(current_bfield))
            filepath = current_scandata.info['Filepath']
            filename = filepath.split('\\')[-1]
            title_items.append(filename.split('_')[3])
            title_str = ", ".join(title_items)
    
            # PLOT SCANDATA
            axes = plt.subplot(len(plot_scandata_list), 1, plot_ind + 1)
    #        axes.set_title(title_str)
            fitfunction = current_model.fitfunction
            yfield = current_model.yfield
            if yfield is None:
                yfield = current_scandata.yfield
            fitdata = current_scandata.get_field_fitdata(yfield)
            if fitdata is None:
                continue
            if figure_dict['forced_fitparams'] is not None:
                fitparams = figure_dict['forced_fitparams']
                fitparamstds = 0.0 * fitparams
            else:
                fitparams = fitdata.fitparams
                fitparamstds = fitdata.fitparamstds
            xvals, yvals, yerrvals = current_scandata.get_field_xyyerr(yfield)
            fityvals = model.fitfunction(xvals, *fitparams)
            if current_scandata.info['IsTRKR?'] is True:
                xvals = xvals.copy()
                xvals[xvals > 10000] -= LASER_REPRATE
            if yerrvals is not None:
                axes.errorbar(xvals, yvals, yerrvals, fmt='bd')
            else:
                axes.plot(xvals, yvals, 'bd')
            plt.ylim(ymax=(np.min(yvals) +
                            1.8 * (np.max(yvals) - np.min(yvals))))
            plt.yticks([0, 0.99 * axes.get_ybound()[-1]])
            axes.text(0.05, 0.95, title_str, horizontalalignment='left',
                      verticalalignment='top', transform=axes.transAxes)
            if plot_ind < len(scandata_indices) - 1:
                plt.xticks([])
            if plot_ind == 0:
                plt.title(figure_dict['title'])
            if not figure_dict['ignore_fit']:
                axes.plot(xvals, fityvals, 'r-')
                if 'osc_period' in fitdata.fitparamlabels:
                    param_ind = list(fitdata.fitparamlabels).index('osc_period')
                    gfactor_str = "osc_period: {:.0f}".format(fitparams[param_ind])
                    gfactor_str += " +- {:.2f}".format(fitparamstds[param_ind])
                elif 'gfactor' in fitdata.fitparamlabels:
                    param_ind = list(fitdata.fitparamlabels).index('gfactor')
                    gfactor_str = "gfactor: {:.3f}".format(fitparams[param_ind])
                    gfactor_str += " +- {:.3f}".format(fitparamstds[param_ind])
                else:
                    gfactor_str = ""
                axes.text(0.95, 0.95, gfactor_str, horizontalalignment='right',
                          verticalalignment='top', transform=axes.transAxes)

# %%
if False:
# %%
    free_param_indices = np.argwhere(model.get_fit_params_is_free_param())
    free_param_labels = \
        list(np.array(model.get_fit_params_labels())[free_param_indices])

    scandata_list_to_plot = [scandataset_list[11].scandata_list[3]]
    num_samples = 100
    param1ind = free_param_labels.index('pulse_amplitude')
    param2ind = free_param_labels.index('species_amp_ratio')

    param_indices = [param1ind, param2ind]
    for scandata in scandata_list_to_plot:
        fitdata = scandata.get_field_fitdata(yfield)
        freeindices = np.array(fitdata.freeparamindices)
        fitparams = np.array([fitdata.fitparams[ind]
                              for ind in freeindices])  # have to avoid {}
        fitparamstds = np.array(fitdata.fitparamstds)[freeindices]
        paramlabels = np.array(fitdata.fitparamlabels)[freeindices]
        covmat = fitdata.covariancematrix
        if not np.all(np.linalg.eigvals(covmat) >= 0):
            print("error, covariance matrix " +
                  "not positive semidefinite, skipping scandata")
            continue

        distribution = np.random.multivariate_normal(fitparams, covmat,
                                                     num_samples)
        axes = plt.subplot(1,2,1)
        axes.add_patch(plt.Rectangle((fitparams - fitparamstds)[param_indices],
                                     *(2 * fitparamstds)[param_indices],
                                     fill=False))
#        plt.plot(*fitparams[plot2dindices], 'ro', markersize=20)
        axes.plot(*distribution[:, param_indices].T, 'bd')
        plt.xlabel(paramlabels[param1ind], fontdict={'size': 16})
        plt.ylabel(paramlabels[param2ind], fontdict={'size': 16})
        plt.subplot(1,2,2)
        xvals, yvals = scandata.xy
        if current_scandata.info['IsTRKR?'] is True:
            xvals = xvals.copy()
            xvals[xvals > 10000] -= LASER_REPRATE
        plt.plot(xvals, yvals, 'bo')
        for fit_param_set in distribution[:, :]:
            fityvals = fitdata.partialfcn(xvals, *fit_param_set)
#            if np.max(np.abs(fityvals)) < 2 * np.max(np.abs(yvals)):
            plt.plot(xvals, fityvals, ':')


