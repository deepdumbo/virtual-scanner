"""
This script does T1 mapping of dicom images

Author: Enlin Qian
Date: 04/29/2019
Version 2.0
Copyright of the Board of Trustees of  Columbia University in the City of New York
"""

import argparse
import matplotlib.pyplot as plt
import numpy as np
import pydicom
from scipy.optimize import curve_fit
import os
import time


def main(dicom_file_path: str, TR: str, TE: str, TI: str, pat_id: str):  # TI should be in second
    """
    Return T1 mapping of a series of IRSE images with variable TI.

    Parameters
    ----------
    dicom_file_path: folder path where all dicom files are
    TI: TI values used in IRSE experiments
    TR: TR values used in IRSE experiments, should be constant

    Returns
    -------
    T1_map: T1 map generated based on input images and TI TR values
    """
    TR = np.fromstring(TR, dtype=int, sep=',')
    TE = np.fromstring(TE, dtype=int, sep=',')
    TI = np.fromstring(TI, dtype=int, sep=',')
    lstFilesDCM = []  # create an empty list
    for dirName, subdirList, fileList in os.walk(dicom_file_path):
        for filename in fileList:
            if ".dcm" in filename.lower():  # check whether the file's DICOM
                lstFilesDCM.append(os.path.join(dirName, filename))

    ref_image = pydicom.read_file(lstFilesDCM[0])  # Get ref file
    image_size = (int(ref_image.Rows), int(ref_image.Columns), len(lstFilesDCM))  # Load dimensions based on the number of rows, columns, and slices (along the Z axis)
    image_data_final = np.zeros(image_size, dtype=ref_image.pixel_array.dtype)

    for filenameDCM in lstFilesDCM:
        ds = pydicom.read_file(filenameDCM)  # read the file
        image_data_final[:, :, lstFilesDCM.index(filenameDCM)] = ds.pixel_array  # store the raw image data
    image_data_final = image_data_final.astype(np.float64)  # convert data type

    image_data_final = np.divide(image_data_final, np.amax(image_data_final))
    T1_map = np.zeros([image_size[0], image_size[1]])
    for n2 in range(image_size[0]):
        for n3 in range(image_size[1]):
            y_data = image_data_final[n2, n3, :]
            n4 = 0
            min_loc = np.argmin(y_data)
            while n4<min_loc:
                y_data[n4] = -y_data[n4]
                n4 = n4+1

            popt, pcov = curve_fit(T1_sig_eq, (TI, TR), y_data, p0=(0.278498218867048, 0.546881519204984, 0.398930085350989), bounds=(0, 6))
            T1_map[n2, n3] = popt[1]
    timestr = time.strftime("%Y%m%d%H%M%S")
    # plt.figure()
    # plt.imshow(T1_map, cmap='hot')
    # plt.show()

    mypath='./src/coms/coms_ui/static/ana/outputs/'+ pat_id

    if not os.path.isdir(mypath):
        os.makedirs(mypath)

    plt.imsave(mypath +'/T1_map' + timestr + '.png', T1_map, cmap='hot')
    filename = "T1_map" + timestr + ".png"


    return filename

def T1_sig_eq(X, a, b, c):
    """
    Generate an exponential function for curve fitting

    Parameters
    ----------
    x: independent variables
    y: independent variables
    a: curve fitting parameters
    b: curve fitting parameters
    c: curve fitting parameters

    Returns
    -------
    exponential function used for T1 curve fitting

    """
    x, y = X
    return a * (1 - 2 * np.exp(-x / b) + np.exp(-y / b)) + c
