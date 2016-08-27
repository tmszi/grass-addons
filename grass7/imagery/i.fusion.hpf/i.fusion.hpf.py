#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
 MODULE:       i.fusion.hpf

 AUTHOR(S):    Nikos Alexandris <nik@nikosalexandris.net>
               Converted from a bash shell script | Trikala, Nov. 2014

               Panagiotis Mavrogiorgos <pmav99@gmail.com>
               Some refactoring | Oct 2015

 PURPOSE:      HPF Resolution Merge -- Algorithm Replication in GRASS GIS

               Module to combine high-resolution panchromatic data with
               lower resolution multispectral data, resulting in an output
               with both excellent detail and a realistic representation of
               original multispectral scene colors.

               The process involves a convolution using a High Pass Filter
               (HPF) on the high resolution data, then combining this with
               the lower resolution multispectral data.

               Optionally, a linear histogram matching technique is performed
               in a  way that matches the resulting Pan-Sharpened imaged to
               them statistical mean and standard deviation of the original
               multi-spectral image. Credits for how to implement this
               technique go to GRASS-GIS developer Moritz Lennert.


               Source: "Optimizing the High-Pass Filter Addition Technique for
               Image Fusion", Ute G. Gangkofner, Pushkar S. Pradhan,
               and Derrold W. Holcomb (2008)

               Figure 1:

+-----------------------------------------------------------------------------+
|  Pan Img ->  High Pass Filter  ->  HP Img                                   |
|                                       |                                     |
|                                       v                                     |
|  MSx Img ->  Weighting Factors ->  Weighted HP Img                          |
|        |                              |                                     |
|        |                              v                                     |
|        +------------------------>  Addition to MSx Img  =>  Fused MSx Image |
+-----------------------------------------------------------------------------+

 COPYRIGHT:    (C) 2014 - 2015 by the GRASS Development Team

               This program is free software under the GNU General Public
               License (>=v2). Read the file COPYING that comes with GRASS
               for details.
"""

#%Module
#%  description: Fusing high resolution Panchromatic and low resolution Multi-Spectral data based on the High-Pass Filter Addition technique (Gangkofner, 2008)
#%  keywords: imagery
#%  keywords: fusion
#%  keywords: sharpening
#%  keywords: high pass filter
#%  keywords: HPFA
#%End

#%flag
#%  key: l
#%  description: Linearly match histogram of Pan-sharpened output to Multi-Spectral input
#%end

#%flag
#%  key: 2
#%  description: 2-Pass Processing (recommended) for large resolution ratio (>=5.5)
#%end

#%flag
#%  key: c
#%  description: Match color table of Pan-Sharpened output to Multi-Spectral input
#%end

#%option G_OPT_R_INPUT
#% key: pan
#% key_desc: filename
#% description: High resolution Panchromatic image
#% required : yes
#%end

#%option G_OPT_R_INPUTS
#% key: msx
#% key_desc: filename(s)
#% description: Low resolution Multi-Spectral image(s)
#% required: yes
#% multiple: yes
#%end

#%option G_OPT_R_BASENAME_OUTPUT
#% key: suffix
#% key_desc: suffix string
#% type: string
#% label: Suffix for output image(s)
#% description: Names of Pan-Sharpened image(s) will end with this suffix
#% required: yes
#% answer: hpf
#%end

#%option
#% key: ratio
#% key_desc: rational number
#% type: double
#% label: Custom ratio
#% description: Custom ratio overriding standard calculation
#% options: 1.0-10.0
#% guisection: High Pass Filter
#% required: no
#%end

#%option
#% key: center
#% key_desc: string
#% type: string
#% label: Center cell value
#% description: Center cell value of the High-Pass-Filter
#% descriptions: Level of center value (low, mid, high)
#% options: low,mid,high
#% required: no
#% answer: low
#% guisection: High Pass Filter
#% multiple : no
#%end

#%option
#% key: center2
#% key_desc: string
#% type: string
#% label: 2nd Pass center cell value
#% description: Center cell value for the second High-Pass-Filter (use -2 flag)
#% descriptions: Level of center value for second pass
#% options: low,mid,high
#% required: no
#% answer: low
#% guisection: High Pass Filter
#% multiple : no
#%end

#%option
#% key: modulation
#% key_desc: string
#% type: string
#% label: Modulation level
#% description: Modulation level weighting the HPF image determining crispness
#% descriptions: Levels of modulating factors
#% options: min,mid,max
#% required: no
#% answer: mid
#% guisection: Crispness
#% multiple : no
#%end

#%option
#% key: modulation2
#% key_desc: string
#% type: string
#% label: 2nd Pass modulation level (use -2 flag)
#% description: Modulation level weighting the second HPF image determining crispness (use -2 flag)
#% descriptions: mid;Mid: 0.35;min;Minimum: 0.25;max;Maximum: 0.5;
#% options: min,mid,max
#% required: no
#% answer: mid
#% guisection: Crispness
#% multiple : no
#%end

#%option
#% key: trim
#% key_desc: rational number
#% type: double
#% label: Trimming factor
#% description: Trim output border pixels by a factor of the pixel size of the low resolution image. A factor of 1.0 may suffice.
#% guisection: High Pass Filter
#% required: no
#%end

# StdLib
import os
import sys
import atexit

# check if within a GRASS session?
if "GISBASE" not in os.environ:
    print "You must be in GRASS GIS to run this program."
    sys.exit(1)

# PyGRASS
import grass.script as grass
from grass.pygrass.modules.shortcuts import general as g
from grass.pygrass.raster.abstract import Info
from grass.pygrass.utils import get_lib_path

# add "etc" directory to $PATH
path = get_lib_path("i.fusion.hpf", "")
if path is None:
    raise ImportError("Not able to find the path %s directory." % path)
sys.path.append(path)

# import modules from "etc"
from high_pass_filter import get_high_pass_filter, get_modulator_factor, get_modulator_factor2


def run(cmd, **kwargs):
    """Pass arbitrary number of key-word arguments to grass commands and the
    "quiet" flag by default."""
    grass.run_command(cmd, quiet=True, **kwargs)


def cleanup():
    """Clean up temporary maps"""
    pattern = 'tmp.{pid}*'.format(pid=os.getpid())
    run('g.remove', flags="f", type="raster", pattern=pattern)


def avg(img):
    """Retrieving Average of input image"""
    uni = grass.parse_command("r.univar", map=img, flags='g')
    avg = float(uni['mean'])
    return avg


def stddev(img):
    """Retrieving Standard Deviation of input image"""
    uni = grass.parse_command("r.univar", map=img, flags='g')
    sd = float(uni['stddev'])
    return sd


def hpf_weight(low_sd, hpf_sd, mod, pss):
    """Returning an appropriate weighting value for the
    High Pass Filtered image. The required inputs are:
    - low_sd:   StdDev of Low resolution image
    - hpf_sd:   StdDev of High Pass Filtered image
    - mod:      Appropriate Modulating Factor determining image crispness
    - pss:      Number of Pass (1st or 2nd)"""
    wgt = low_sd / hpf_sd * mod  # mod: modulator
    msg = '   >> '
    if pss == 2:
        msg += '2nd Pass '
    msg += 'Weighting = {l:.{dec}f} / {h:.{dec}f} * {m:.{dec}f} = {w:.{dec}f}'
    msg = msg.format(l=low_sd, h=hpf_sd, m=mod, w=wgt, dec=3)
    g.message(msg, flags='v')
    return wgt


def hpf_ascii(center, filter, tmpfile, second_pass):
    """Exporting a High Pass Filter in a temporary ASCII file"""
    # structure informative message
    msg = "   > {m}Filter Properties: center: {c}"
    msg_pass = '2nd Pass ' if second_pass else ''
    msg = msg.format(m=msg_pass, c=center)
    g.message(msg, flags='v')

    # open, write and close file
    with open(tmpfile, 'w') as asciif:
        asciif.write(filter)


# main program

def main():

    pan = options['pan']
    msxlst = options['msx'].split(',')
    outputsuffix = options['suffix']
    custom_ratio = options['ratio']
    center = options['center']
    center2 = options['center2']
    modulation = options['modulation']
    modulation2 = options['modulation2']

    if options['trim']:
        trimming_factor = float(options['trim'])
    else:
        trimming_factor = False

    histogram_match = flags['l']
    second_pass = flags['2']
    color_match = flags['c']

#    # Check & warn user about "ns == ew" resolution of current region ======
#    region = grass.region()
#    nsr = region['nsres']
#    ewr = region['ewres']
#
#    if nsr != ewr:
#        msg = ('>>> Region's North:South ({ns}) and East:West ({ew}) '
#               'resolutions do not match!')
#        msg = msg.format(ns=nsr, ew=ewr)
#        g.message(msg, flags='w')

    mapset = grass.gisenv()['MAPSET']  # Current Mapset?
    region = grass.region()  # and region settings

    # List images and their properties

    imglst = [pan]
    imglst.extend(msxlst)  # List of input imagery

    images = {}
    for img in imglst:  # Retrieving Image Info
        images[img] = Info(img, mapset)
        images[img].read()

    panres = images[pan].nsres  # Panchromatic resolution

    grass.use_temp_region()  # to safely modify the region
    run('g.region', res=panres)  # Respect extent, change resolution
    g.message("|! Region's resolution matched to Pan's ({p})".format(p=panres))

    # Loop Algorithm over Multi-Spectral images

    for msx in msxlst:
        g.message("\nProcessing image: {m}".format(m=msx))

        # Tracking command history -- Why don't do this all r.* modules?
        cmd_history = []

        #
        # 1. Compute Ratio
        #

        g.message("\n|1 Determining ratio of low to high resolution")

        # Custom Ratio? Skip standard computation method.
        if custom_ratio:
            ratio = float(custom_ratio)
            g.message('Using custom ratio, overriding standard method!',
                      flags='w')

        # Multi-Spectral resolution(s), multiple
        else:
            # Image resolutions
            g.message("   > Retrieving image resolutions")

            msxres = images[msx].nsres

            # check
            if panres == msxres:
                msg = ("The Panchromatic's image resolution ({pr}) "
                       "equals to the Multi-Spectral's one ({mr}). "
                       "Something is probably not right! "
                       "Please check your input images.")
                msg = msg.format(pr=panres, mr=msxres)
                grass.fatal(_(msg))

            # compute ratio
            ratio = msxres / panres
            msg_ratio = ('   >> Resolution ratio '
                         'low ({m:.{dec}f}) to high ({p:.{dec}f}): {r:.1f}')
            msg_ratio = msg_ratio.format(m=msxres, p=panres, r=ratio, dec=3)
            g.message(msg_ratio)

        # 2nd Pass requested, yet Ratio < 5.5
        if second_pass and ratio < 5.5:
            g.message("   >>> Resolution ratio < 5.5, skipping 2nd pass.\n"
                      "   >>> If you insist, force it via the <ratio> option!",
                      flags='i')
            second_pass = bool(0)

        #
        # 2. High Pass Filtering
        #

        g.message('\n|2 High Pass Filtering the Panchromatic Image')

        tmpfile = grass.tempfile()  # Temporary file - replace with os.getpid?
        tmp = 'tmp.' + grass.basename(tmpfile)  # use its basenam
        tmp_pan_hpf = '{tmp}_pan_hpf'.format(tmp=tmp)  # HPF image
        tmp_msx_blnr = '{tmp}_msx_blnr'.format(tmp=tmp)  # Upsampled MSx
        tmp_msx_hpf = '{tmp}_msx_hpf'.format(tmp=tmp)  # Fused image
        tmp_hpf_matrix = grass.tempfile()  # ASCII filter

        # Construct and apply Filter
        hpf = get_high_pass_filter(ratio, center)
        hpf_ascii(center, hpf, tmp_hpf_matrix, second_pass)
        run('r.mfilter', input=pan, filter=tmp_hpf_matrix,
            output=tmp_pan_hpf,
            title='High Pass Filtered Panchromatic image',
            overwrite=True)

        # 2nd pass
        if second_pass and ratio > 5.5:
            # Temporary files
            tmp_pan_hpf_2 = '{tmp}_pan_hpf_2'.format(tmp=tmp)  # 2nd Pass HPF image
            tmp_hpf_matrix_2 = grass.tempfile()  # 2nd Pass ASCII filter
            # Construct and apply 2nd Filter
            hpf_2 = get_high_pass_filter(ratio, center2)
            hpf_ascii(center2, hpf_2, tmp_hpf_matrix_2, second_pass)
            run('r.mfilter',
                input=pan,
                filter=tmp_hpf_matrix_2,
                output=tmp_pan_hpf_2,
                title='2-High-Pass Filtered Panchromatic Image',
                overwrite=True)

        #
        # 3. Upsampling low resolution image
        #

        g.message("\n|3 Upsampling (bilinearly) low resolution image")

        run('r.resamp.interp',
            method='bilinear', input=msx, output=tmp_msx_blnr, overwrite=True)

        #
        # 4. Weighting the High Pass Filtered image(s)
        #

        g.message("\n|4 Weighting the High-Pass-Filtered image (HPFi)")

        # Compute (1st Pass) Weighting
        msg_w = "   > Weighting = StdDev(MSx) / StdDev(HPFi) * " \
            "Modulating Factor"
        g.message(msg_w)

        # StdDev of Multi-Spectral Image(s)
        msx_avg = avg(msx)
        msx_sd = stddev(msx)
        g.message("   >> StdDev of <{m}>: {sd:.3f}".format(m=msx, sd=msx_sd))

        # StdDev of HPF Image
        hpf_sd = stddev(tmp_pan_hpf)
        g.message("   >> StdDev of HPFi: {sd:.3f}".format(sd=hpf_sd))

        # Modulating factor
        modulator = get_modulator_factor(modulation, ratio)
        g.message("   >> Modulating Factor: {m:.2f}".format(m=modulator))

        # weighting HPFi
        weighting = hpf_weight(msx_sd, hpf_sd, modulator, 1)

        #
        # 5. Adding weighted HPF image to upsampled Multi-Spectral band
        #

        g.message("\n|5 Adding weighted HPFi to upsampled image")
        fusion = '{hpf} = {msx} + {pan} * {wgt}'
        fusion = fusion.format(hpf=tmp_msx_hpf, msx=tmp_msx_blnr,
                               pan=tmp_pan_hpf, wgt=weighting)
        grass.mapcalc(fusion)

        # command history
        hst = 'Weigthing applied: {msd:.3f} / {hsd:.3f} * {mod:.3f}'
        cmd_history.append(hst.format(msd=msx_sd, hsd=hpf_sd, mod=modulator))

        if second_pass and ratio > 5.5:

            #
            # 4+ 2nd Pass Weighting the High Pass Filtered image
            #

            g.message("\n|4+ 2nd Pass Weighting the HPFi")

            # StdDev of HPF Image #2
            hpf_2_sd = stddev(tmp_pan_hpf_2)
            g.message("   >> StdDev of 2nd HPFi: {h:.3f}".format(h=hpf_2_sd))

            # Modulating factor #2
            modulator_2 = get_modulator_factor2(modulation2)
            msg = '   >> 2nd Pass Modulating Factor: {m:.2f}'
            g.message(msg.format(m=modulator_2))

            # 2nd Pass weighting
            weighting_2 = hpf_weight(msx_sd, hpf_2_sd, modulator_2, 2)

            #
            # 5+ Adding weighted HPF image to upsampled Multi-Spectral band
            #

            g.message("\n|5+ Adding small-kernel-based weighted 2nd HPFi "
                      "back to fused image")

            add_back = '{final} = {msx_hpf} + {pan_hpf} * {wgt}'
            add_back = add_back.format(final=tmp_msx_hpf, msx_hpf=tmp_msx_hpf,
                                       pan_hpf=tmp_pan_hpf_2, wgt=weighting_2)
            grass.mapcalc(add_back)

            # 2nd Pass history entry
            hst = "2nd Pass Weighting: {m:.3f} / {h:.3f} * {mod:.3f}"
            cmd_history.append(hst.format(m=msx_sd, h=hpf_2_sd, mod=modulator_2))

        if color_match:
            g.message("\n|* Matching output to input color table")
            run('r.colors', map=tmp_msx_hpf, raster=msx)

        #
        # 6. Stretching linearly the HPF-Sharpened image(s) to match the Mean
        #     and Standard Deviation of the input Multi-Sectral image(s)
        #

        if histogram_match:

            # adapt output StdDev and Mean to the input(ted) ones
            g.message("\n|+ Matching histogram of Pansharpened image "
                      "to %s" % (msx), flags='v')

            # Collect stats for linear histogram matching
            msx_hpf_avg = avg(tmp_msx_hpf)
            msx_hpf_sd = stddev(tmp_msx_hpf)

            # expression for mapcalc
            lhm = '{out} = ({hpf} - {hpfavg}) / {hpfsd} * {msxsd} + {msxavg}'
            lhm = lhm.format(out=tmp_msx_hpf, hpf=tmp_msx_hpf,
                             hpfavg=msx_hpf_avg, hpfsd=msx_hpf_sd,
                             msxsd=msx_sd, msxavg=msx_avg)

            # compute
            grass.mapcalc(lhm, quiet=True, overwrite=True)

            # update history string
            cmd_history.append("Linear Histogram Matching: %s" % lhm)

        #
        # Optional. Trim to remove black border effect (rectangular only)
        #

        if trimming_factor:

            tf = trimming_factor

            # communicate
            msg = '\n|* Trimming output image border pixels by '
            msg += '{factor} times the low resolution\n'.format(factor=tf)
            nsew = '   > Input extent: n: {n}, s: {s}, e: {e}, w: {w}'
            nsew = nsew.format(n=region.n, s=region.s, e=region.e, w=region.w)
            msg += nsew

            g.message(msg)

            # re-set borders
            region.n -= tf * images[msx].nsres
            region.s += tf * images[msx].nsres
            region.e -= tf * images[msx].ewres
            region.w += tf * images[msx].ewres

            # communicate and act
            msg = '   > Output extent: n: {n}, s: {s}, e: {e}, w: {w}'
            msg = msg.format(n=region.n, s=region.s, e=region.e, w=region.w)
            g.message(msg)

            # modify only the extent
            run('g.region',
                n=region.n, s=region.s, e=region.e, w=region.w)
            trim = "{out} = {input}".format(out=tmp_msx_hpf, input=tmp_msx_hpf)
            grass.mapcalc(trim)

        #
        # End of Algorithm

        # history entry
        run("r.support", map=tmp_msx_hpf, history="\n".join(cmd_history))

        # add suffix to basename & rename end product
        msx_name = "{base}.{suffix}"
        msx_name = msx_name.format(base=msx.split('@')[0], suffix=outputsuffix)
        run("g.rename", raster=(tmp_msx_hpf, msx_name))

        # remove temporary files
        cleanup()

    # visualising-related information
    grass.del_temp_region()  # restoring previous region settings
    g.message("\n|! Original Region restored")
    g.message("\n>>> Hint, rebalancing colors (via i.colors.enhance) "
              "may improve appearance of RGB composites!",
              flags='i')

if __name__ == "__main__":
    options, flags = grass.parser()
    atexit.register(cleanup)
    sys.exit(main())