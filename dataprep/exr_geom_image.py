import os
import cv2
import argparse
import json
import numpy as np
import sys
import multiprocessing as mp
from multiprocessing import Process
import random

random.seed()

#sys.path.append("/home/will/projects/legoproj")

#import cvscripts
#from cvscripts import feature_utils as fu
import feature_utils as fu

parser = argparse.ArgumentParser()
parser.add_argument('-p', '--path', dest='path',required=True,help='JSON data path?')
parser.add_argument('-n', '--num', dest='num',required=False,type=int,help='File num?')
args = parser.parse_args()

with open(args.path) as json_file:
    data = json.load(json_file)


hues_objdata = {}

for entry in data["ids"]:

    if entry == "0":
        continue

    name = data["ids"][entry]
    objentry = data["objects"][name]

    #print(objentry)

    l2w = fu.matrix_from_string(objentry["modelmat"])
    w2l = np.linalg.inv(l2w)

    bbl = np.array(objentry["bbl"])
    bbh = np.array(objentry["bbh"])

    dims = bbh - bbl

    #if "WingL.002" in name:
    #    print(dims)

    info = {}
    info["w2l"] = w2l
    info["lows"] = bbl

    info["dims"] = dims
    info["name"] = data["ids"][entry]

    hues_objdata[int(entry)] = info


rows = np.arange(256)
cols = np.arange(256)

r,c = np.meshgrid(rows,cols)
inds = np.stack((c,r),axis=-1).astype(np.float32)



abspath = os.path.abspath(args.path)
abspath = abspath.replace(abspath.split("/")[-1],"")

write_path = abspath + "geom"

if not os.path.exists(write_path):
    os.mkdir(write_path)


classes = ["WingR","WingL","Brick","Pole"]


def getClass(objname):
    for clss in classes:
        if clss in objname:
            return clss
    return None


def getObjFromHue(hue):
    hue = int(round(hue/5))
    name = data["ids"][str(hue)]
    
    return name



def separate(mask):
    
    kernel = np.ones((2,2), np.uint8) 
    maskdict = {}

    hsvmask = cv2.cvtColor(mask,cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsvmask],[0],None,[180],[0,179])
    
    hues=[]
    for j,e in enumerate(hist):
        if e[0] > 20:
            hues.append(j)

    for hue in hues:

        threshed = cv2.inRange(hsvmask, (hue-1,0,100), (hue+1,255,255))
        threshed = cv2.medianBlur(threshed.astype(np.uint8), 3)
        threshed = cv2.dilate(threshed, kernel, iterations=1)

        #if np.sum(threshed) <= 255*100:
        #    continue;

        maskdict[hue] = threshed

    return maskdict



def overlay(i):

    print(i)

    tag = "{:0>4}".format(i)

    viewmat = fu.matrix_from_string(data["viewmats"][i])
    toworld = np.linalg.inv(viewmat)
    
    maskpath = os.path.join(abspath,"{}_masks.png".format(tag))
    mask = cv2.imread(maskpath)
    maskraw = cv2.resize(mask, (256,256), cv2.INTER_NEAREST)
    mask = cv2.cvtColor(maskraw,cv2.COLOR_BGR2HSV)[:,:,0]

    depthpath = os.path.join(abspath,"{}_npdepth.npy".format(tag))
    depthmap = np.load(depthpath,allow_pickle=False)

    projmat = fu.matrix_from_string(data["projection"])


    d = np.reshape(depthmap,(512,512,1))
    d = d[0::2,0::2]

    f = np.concatenate((inds,d),axis=-1)

    kernel = np.ones((3,3),np.uint8)

    mask = np.reshape(mask,(256,256,1))
    g = np.concatenate((f,mask),axis=-1)

    output = np.apply_along_axis(func1d=fu.unproject_to_local, axis=-1, arr=g, infodict=hues_objdata, toworld=toworld, p=projmat, dims=(256,256))
    output = (np.around(255 * output[:,:,2::-1])).astype(np.uint8)

    masks = separate(maskraw)
    mask = np.zeros((256,256)).astype(np.uint8)

    for hue in masks:
        objname = getObjFromHue(hue)
        if objname:
            objclass = objname.split(".")[0]
            if objclass == "Pole":
                mask += masks[hue]

    #mask = cv2.inRange( mask, (0,2,2), (179,255,255) )
    output = cv2.bitwise_and(output,output,mask=mask)

    wr = os.path.join(write_path,"{}_geom.png".format(tag))
    cv2.imwrite(wr,output)


def iterOverlay(indices):
    for ind in indices:
        overlay(ind)


indices = np.arange(data["runs"]) if args.num is None else np.arange(args.num) 
cores = mp.cpu_count()
num_procs = 1 if len(indices) < cores else cores
indices_lists = np.array_split(indices, num_procs)

processes = []

#indices_lists=np.array([[1]])

for ilist in indices_lists:
    processes.append( Process(target=iterOverlay, args=(ilist,)) )

for process in processes:
    process.start()

for process in processes:
    process.join()
