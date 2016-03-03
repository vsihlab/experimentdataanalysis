# -*- coding: utf-8 -*-
"""
Created on Tue Feb 23 16:22:19 2016

@author: Michael
"""

from concurrent.futures import ProcessPoolExecutor
import time


# %%
def fcn_with_unpacked_args(fcn_arglist_tuple):
    """
    Allows variable length argument list for ProcessPoolExecutor
    at the cost of being a bit confusing. To use, need to pack
    function alongside arguments. For example, if you want to map
    the function "map_function" with arg lists from
    input_args_iterable, you would write:
    fcn_arglist_tuples = ((map_function, args)
                          for args in input_args_iterable)
    map(fcn_with_unpacked_args, fcn_arglist_tuples)
    """
    fcn, arglist = fcn_arglist_tuple
    return fcn(*arglist)


def pack_args_for_fcn(function, input_args_iterable):
    """
    implements
    fcn_arglist_tuples = ((map_function, args)
                          for args in input_args_iterable)
    """
    return ((function, args) for args in input_args_iterable)


# %%
def multiprocessable_map(processfunction, input_args_iterable,
                         multiprocessing=False):
    """
    multiprocessing = False:
    identical to
    for input_args in input_args_iterable:
        yield processfunction(*input_args)
    ---
    multiprocessing = True:
    Generic ProcessPoolExecutor loop. Supports any arbitrary
    function, whether processes or threads or faster may depend
    on the function and computer used.
    WARNING: pickle fails unless the input/output object classes
        are defined via IMPORT statement. Cannot define in module!
    WARNING: do not call even indirectly from interpreter, run
        script with main() method!
    WARNING: numpy's curve_map is not threadsafe in a way that may
        cause issues. Use multiprocessing instead (faster anyway)
    WARNING: pickle has to send the code to be run, and it looks
        like it cannot handle sending functions that dynamically
        create local subfunctions or are local subfunctions
        themselves. Avoid that, I guess.
            e.g. sending this instead of processfunction failed:
                def safer_map_function(inputdata):
                    try:
                        return processfunction(inputdata)
                        except <stuff>...

    Generator yielding each of the outputs of the processfunction
    acting on each input value.

    Positional arguments:
        processfunction -- takes input_args, returns anything picklable
        input_args_iterable -- iterable pointing to a series of argument
                                lists for the mapped function
    """
    if multiprocessing:
        packed_fcn_args = pack_args_for_fcn(processfunction,
                                            input_args_iterable)
        start_processing_time = time.time()
        with ProcessPoolExecutor(max_workers=None) as executor:
            output_iter = executor.map(fcn_with_unpacked_args,
                                       packed_fcn_args,
                                       timeout=30, chunksize=1)
        elapsed_processing_time = time.time() - start_processing_time
        print('{} seconds elapsed during multiprocessing'.format(
                                                    elapsed_processing_time))
        for output in output_iter:
            yield output
    else:
        for input_args in input_args_iterable:
            yield processfunction(*input_args)
