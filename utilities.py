# -*- coding: utf-8 -*-
# <nbformat>3.0</nbformat>

# <codecell>

from skimage.filter import threshold_otsu, threshold_adaptive, gaussian_filter
from skimage.color import color_dict
from skimage.segmentation import clear_border
from skimage.morphology import binary_dilation, binary_erosion, watershed, remove_small_objects
from skimage.measure import regionprops, label
from skimage.restoration import denoise_bilateral
import numpy as np

def foreground_mask(img):
#     t_img = gaussian_filter(img, sigma=3) < 220./255.
    t_img = denoise_bilateral(img) < 220./255.

    labels, n_labels = label(t_img, neighbors=4, return_num=True)
    
    reg = regionprops(labels+1)
    all_areas = np.array([r.area for r in reg])
    
    a = np.concatenate([labels[0,:] ,labels[-1,:] ,labels[:,0] ,labels[:,-1]])
    border_labels = np.unique(a)
    
    border_labels_large = np.extract(all_areas[border_labels] > 250, border_labels)

    mask = np.ones_like(img, dtype=np.bool)
    for i in border_labels_large:
        if i != all_areas.argmax():
            mask[labels==i] = 0

    mask = remove_small_objects(mask, min_size=64, connectivity=1, in_place=False)
            
    return mask


def crop_image(img):
    blurred = gaussian_filter(img, 20)
    thresholded = blurred < threshold_otsu(blurred)
    slc = measurements.find_objects(thresholded)[0]

#     margin = 100
#     xstart = max(slc[0].start - margin, 0)
#     xstop = min(slc[0].stop + margin, img.shape[0])
#     ystart = max(slc[1].start - margin, 0)
#     ystop = min(slc[1].stop + margin, img.shape[1])
#     cutout = img[xstart:xstop, ystart:ystop]
    return cutout

# <codecell>

from copy_reg import pickle
from types import MethodType

def _pickle_method(method):
    func_name = method.im_func.__name__
    obj = method.im_self
    cls = method.im_class
    return _unpickle_method, (func_name, obj, cls)

def _unpickle_method(func_name, obj, cls):
    for cls in cls.mro():
        try:
            func = cls.__dict__[func_name]
        except KeyError:
            pass
        else:
            break
    return func.__get__(obj, cls)

pickle(MethodType, _pickle_method, _unpickle_method)

# <codecell>

import time
 
def timeit(func=None,loops=1,verbose=False):
    if func != None:
        def inner(*args,**kwargs):
 
            sums = 0.0
            mins = 1.7976931348623157e+308
            maxs = 0.0
            print '==== %s ====' % func.__name__
            for i in range(0,loops):
                t0 = time.time()
                result = func(*args,**kwargs)
                dt = time.time() - t0
                mins = dt if dt < mins else mins
                maxs = dt if dt > maxs else maxs
                sums += dt
                if verbose == True:
                    print '\t%r ran in %2.9f sec on run %s' %(func.__name__,dt,i)
            
            if loops == 1:
                print '%r run time was %2.9f sec' % (func.__name__,sums)
            else:
                print '%r min run time was %2.9f sec' % (func.__name__,mins)
                print '%r max run time was %2.9f sec' % (func.__name__,maxs)
                print '%r avg run time was %2.9f sec in %s runs' % (func.__name__,sums/loops,loops)
            
            return result
 
        return inner
    else:
        def partial_inner(func):
            return timeit(func,loops,verbose)
        return partial_inner

