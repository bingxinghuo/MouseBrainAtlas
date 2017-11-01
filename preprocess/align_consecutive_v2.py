#!/usr/bin/env python

import os
import sys
import json

sys.path.append(os.path.join(os.environ['REPO_DIR'], 'utilities'))
from metadata import *
from utilities2015 import *

import argparse

parser = argparse.ArgumentParser(
    formatter_class=argparse.RawDescriptionHelpFormatter,
    description='Align consecutive images.')

parser.add_argument("stack", type=str, help="stack name")
parser.add_argument("input_dir", type=str, help="input dir")
parser.add_argument("output_dir", type=str, help="output dir")
parser.add_argument("kwargs_str", type=str, help="json-encoded list of dict (keyworded inputs). Each dict entry should have prev_fn and curr_fn. It can optionally have prev_sn and curr_sn if file names are different from section names.")
parser.add_argument("fmt", type=str, help="file format, e.g. tif")

args = parser.parse_args()

stack = args.stack
input_dir = args.input_dir
output_dir = args.output_dir
kwargs_str = json.loads(args.kwargs_str)
fmt = args.fmt

parameter_dir = os.path.join(os.environ['REPO_DIR'], 'preprocess', 'parameters')

rg_param_rigid = os.path.join(parameter_dir, "Parameters_Rigid.txt")
rg_param_mutualinfo = os.path.join(parameter_dir, "Parameters_Rigid_MutualInfo.txt")

if stack in all_alt_nissl_ntb_stacks or stack in all_alt_nissl_tracing_stacks:
    rg_param = rg_param_mutualinfo
else:
    rg_param = rg_param_rigid

failed_pairs = []

for kwarg in kwargs_str:
    prev_fn = kwarg['prev_fn']
    curr_fn = kwarg['curr_fn']
    
    if 'prev_sn' in kwarg and 'curr_sn' in kwarg:
        prev_sn = kwarg['prev_sn']
        curr_sn = kwarg['curr_sn']
        output_subdir = os.path.join(output_dir, curr_sn + '_to_' + prev_sn)
    else:
        output_subdir = os.path.join(output_dir, curr_fn + '_to_' + prev_fn)

    if os.path.exists(output_subdir) and 'TransformParameters.0.txt' in os.listdir(output_subdir):
        sys.stderr.write('Result for aligning %s to %s already exists.\n' % (curr_fn, prev_fn))
        continue

    execute_command('rm -rf \"%s\"' % output_subdir)
    create_if_not_exists(output_subdir)

    ret = execute_command('%(elastix_bin)s -f \"%(fixed_fn)s\" -m \"%(moving_fn)s\" -out \"%(output_subdir)s\" -p \"%(rg_param)s\"' % \
            {'elastix_bin': ELASTIX_BIN,
            'rg_param': rg_param,
            'output_subdir': output_subdir,
            'fixed_fn': os.path.join(input_dir, prev_fn + '.' + fmt),
            'moving_fn': os.path.join(input_dir, curr_fn + '.' + fmt)
            })

    if ret == 1:
        # sys.stderr.write(prev_fn + ' vs. ' + curr_fn + ' failed.\n')
        failed_pairs.append((prev_fn, curr_fn))

import subprocess
hostname = subprocess.check_output("hostname", shell=True).strip()

if len(failed_pairs) > 0:
    with open(os.path.join(output_dir, '%s_failed_pairs_%s.txt' % (stack, hostname.split('.')[0])), 'w') as f:
        for pf, cf in failed_pairs:
            f.write(pf + ' ' + cf + '\n')
            