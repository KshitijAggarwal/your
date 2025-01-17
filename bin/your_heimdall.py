#!/usr/bin/env python3

import argparse
import logging
import os
from datetime import datetime
from multiprocessing import Process

import numpy as np

from your import Your
from your import dada
from your.utils import dispersion_delay


class HeimdallManager:

    def __init__(self, dada_key=None, filename=None, verbosity=None, nsamps_gulp=None, beam=None, baseline_length=None,
                 output_dir=None, dm=None, dm_tol=None, zap_chans=None, max_giant_rate=None, dm_nbits=None, gpu_id=None,
                 no_scrunching=None, scrunching_tol=None, rfi_tol=None,
                 rfi_no_narrow=None, rfi_no_broad=None, boxcar_max=None, fswap=None,
                 min_tscrunch_width=None):
        self.k = dada_key
        self.f = filename
        self.verbosity = verbosity
        self.nsamps_gulp = nsamps_gulp
        self.beam = beam
        self.baseline_length = baseline_length
        self.output_dir = output_dir
        self.dm = dm
        self.dm_tol = dm_tol
        self.zap_chans = zap_chans
        self.max_gaint_rate = max_giant_rate
        self.dm_nbits = dm_nbits
        self.gpu_id = gpu_id
        self.no_scrunching = no_scrunching
        self.scrunching_tol = scrunching_tol
        self.rfi_tol = rfi_tol
        self.rfi_no_narrow = rfi_no_narrow
        self.rfi_no_broad = rfi_no_broad
        self.boxcar_max = boxcar_max
        self.fswap = fswap
        self.min_tscrunch_width = min_tscrunch_width

        if (self.k is None) and (self.f is None):
            raise IOError(f"Need either a dada key or a filterbank file to run")

    def run(self):
        cmd = 'heimdall '
        for attribute, value in self.__dict__.items():
            if value is not None:
                if isinstance(value, list):
                    cmd += str(f' -{attribute} ')
                    cmd += ' '.join(map(str, value))
                elif attribute == 'verbosity':
                    if value in ['V', 'v', 'g', 'G']:
                        cmd += str(f' -{value} ')
                    else:
                        logging.warning(f"Allowed verbosity is v,V,g,G")
                        logging.warning(f"Using v for now!")
                        cmd += f" -v "

                else:
                    cmd += str(f' -{attribute} {value}')

        logging.info(f"Using cmd: \n{cmd}")
        os.system(cmd)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Your Heimdall Fetch FRB",
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('-v', '--verbose', help='Be verbose', action='store_true')
    parser.add_argument('-p', '--probability', help='Detection threshold', default=0.5, type=float)
    parser.add_argument('-f', '--files', help='filterbank or psrfits', nargs='+')
    parser.add_argument('-dm', '--dm', help='DM (eg -dm 10 1000)', type=float, nargs=2, default=[10, 1000])
    parser.add_argument('-g', '--gpu_id', help='GPU ID to run heimdall on', type=int, required=False, default=0)
    parser.add_argument('-o', '--output_dir', help='Output dir for heimdall candidates', type=str, required=False,
                        default=None)
    args = parser.parse_args()

    if args.output_dir is None:
        args.output_dir = "{0}/{1}".format(os.getcwd(), ('.').join(
            os.path.basename(args.files[0]).split('.')[:-1]))
        os.makedirs(args.output_dir, exist_ok=True)

    logging_format = '%(asctime)s - %(funcName)s -%(name)s - %(levelname)s - %(message)s'
    log_filename = args.output_dir + '/' + datetime.utcnow().strftime('your_heimdall_%Y_%m_%d_%H_%M_%S_%f.log')

    if args.verbose:
        logging.basicConfig(filename=log_filename, level=logging.DEBUG, format=logging_format)
        logging.debug("Using debug mode")
    else:
        logging.basicConfig(filename=log_filename, level=logging.INFO, format=logging_format)

    your_object = Your(file=args.files)
    max_delay = dispersion_delay(your_object, dms=np.max(args.dm))
    dispersion_delay_samples = np.ceil(max_delay / your_object.tsamp)
    logging.info(f"Max Dispersion delay = {max_delay} s")
    logging.info(f"Max Dispersion delay = {dispersion_delay_samples} samples")

    nsamps_gulp = int(np.max([(2 ** np.ceil(np.log2(dispersion_delay_samples))), 2 ** 18]))

    your_dada = dada.YourDada(your_object)
    your_dada.setup()

    HM = HeimdallManager(dm=args.dm, dada_key=your_dada.dada_key, boxcar_max=int(32e-3 / your_object.tsamp),
                         verbosity='v', nsamps_gulp=nsamps_gulp, gpu_id=args.gpu_id, output_dir=args.output_dir)

    dada_process = Process(name='To dada', target=your_dada.to_dada)
    heimdall_process = Process(name='Heimdall', target=HM.run)

    dada_process.start()
    heimdall_process.start()

    try:
        heimdall_process.join()
        dada_process.join()
    except KeyboardInterrupt:
        heimdall_process.terminate()
        dada_process.terminate()

    your_dada.teardown()
    logging.info("Destroyed dada buffers")
