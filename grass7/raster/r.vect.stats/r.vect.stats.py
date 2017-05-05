#!/usr/bin/env python

############################################################################
#
# MODULE:    r.binning
# AUTHOR(S): Vaclav Petras <wenzeslaus gmail com>
# PURPOSE:
# COPYRIGHT: (C) 2017 by Vaclav Petras and the GRASS Development Team
#
#            This program is free software under the GNU General Public
#            License (>=v2). Read the file COPYING that comes with GRASS
#            for details.
#
#############################################################################

#%module
#% description: Bin vector points into a raster map
#% keyword: raster
#% keyword: vector
#% keyword: points
#% keyword: binning
#% overwrite: yes
#%end
#%option G_OPT_V_INPUT
#%end
#%option G_OPT_R_OUTPUT
#%end
#%option G_OPT_DB_COLUMN
#% description: Name of attribute column for statistics
#%end
#%option
#% key: method
#% description: Statistic to use for attribute column
#% options: min,max,range,sum,mean,stddev,variance,coeff_var,median,percentile,skewness,trimmean
#% answer: mean
#%end

import grass.script as gs


def main():
    options, flags = gs.parser()

    vector = options['input']
    layer = 1
    raster = options['output']
    method = 'n'
    z = 3
    sep = 'pipe'
    if options['column']:
        method = options['method']
        z = 4

    out_process = gs.pipe_command(
        'v.out.ascii', input=vector, layer=layer, format='point',
        column=options['column'], separator=sep)
    in_process = gs.start_command(
        'r.in.xyz', input='-', output=raster, method=method, z=z,
        separator=sep, stdin=out_process.stdout)
    in_process.communicate()
    out_process.wait()


if __name__ == "__main__":
    main()
