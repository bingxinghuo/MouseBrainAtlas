# -*- coding: utf-8 -*-
# <nbformat>3.0</nbformat>

# <codecell>

import os, json
from IPython.display import FileLink, Image, FileLinks
from pprint import pprint
import cv2
import numpy as np
from skimage.util import img_as_ubyte
from skimage.color import gray2rgb

# <codecell>

def create_param(param_id, **args):
    param_dict = {
        "n_texton": 20, 
        "max_freq": 0.2, 
        "freq_step": 2,
        "param_id": param_id, 
        "theta_interval": 10, 
        "n_freq": 4,
        'n_superpixels': 2000,
        'slic_compactness': 5,
        'slic_sigma': 10
    }
    param_dict.update(args)    
    json.dump(param_dict, open('../params/param%d.json'%param_id, 'w'))
    
def load_param(param_id):
    param = json.load(open('../params/param%d.json'%param_id, 'r'))
    pprint(param)

# <codecell>

def load_array(suffix, img_name, param_id, cache_dir='scratch'):
    arr_file = os.path.join(cache_dir, img_name,
                        '%s_param%d_%s.npy'%(img_name, param_id,
                                             suffix))
    arr = np.load(arr_file)
    print 'load %s' % (arr_file)
    return arr

def save_array(arr, suffix, img_name, param_id, cache_dir='scratch'):
    arr_file = os.path.join(cache_dir, img_name,
                        '%s_param%d_%s.npy'%(img_name, param_id,
                                             suffix))
    if not os.path.exists(arr_file):
        np.save(arr_file, arr)
        print '%s saved to %s' % (suffix, arr_file)
    else:
        print '%s already exists' % (arr_file)

        
def regulate_images(imgs):
    return np.array(map(regulate_img, imgs))
        
def regulate_img(img):
    if not np.issubsctype(img, np.uint8):
        try:
            img = img_as_ubyte(img)
        except:
            img_norm = (img-img.min()).astype(np.float)/(img.max() - img.min())    
            img = img_as_ubyte(img_norm)
            
    if img.ndim == 2:
        img = gray2rgb(img)
    
    return img
        
def save_img(img, suffix, img_name, param_id, 
             cache_dir='scratch', overwrite=False):
    '''
    img is in uint8 type or float type
    '''
    img = regulate_img(img)
        
    img_fn = get_img_filename(suffix, img_name, param_id, cache_dir, ext='tif')
    if not os.path.exists(img_fn) or overwrite:
        cv2.imwrite(img_fn, img)
        print '%s saved to %s' % (suffix, img_fn)
    else:
        print '%s already exists' % (img_fn)
        
    img_fn = get_img_filename(suffix, img_name, param_id, cache_dir, ext='png')
    if not os.path.exists(img_fn) or overwrite:
        cv2.imwrite(img_fn, img)
        print '%s saved to %s' % (suffix, img_fn)
    else:
        print '%s already exists' % (img_fn)

        
def get_img_filename(suffix, img_name, param_id, cache_dir='scratch', ext='tif'):
#     img_fn = os.path.join(args.cache_dir,
#                 '%s_param%d_%s.png'%(img_name, params['param_id'], suffix))
    img_fn = os.path.join(cache_dir, img_name,
                '%s_param%d_%s.%s'%(img_name, param_id, suffix, ext))
    return img_fn
