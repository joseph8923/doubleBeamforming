# Written by Eileen R. Martin

import numpy as np
import scipy.fftpack as ft
import time
import obspy
from numba import jit



@jit(nopython=True) # this command allows some optimizations over for loops with lots of numpy operations
def shiftFrqData(thisLoc,slownesses,frqs,dataF,Nu,NTh,nFrq):
	# This script calculates the R factor for an array due to a particular sensor.
	#
	# INPUTS:
	# thisLoc, a 1D numpy array with 2 entries (x and y coordinates in meters) describing location of the sensor
	# slownesses, a 3D numpy array with slownesses of interests (# of slownesses, # of angles, 2)
	# 	where slownesses[iu,ith,0] = u*cos(theta) and slownesses[iu,ith,1] = u*sin(theta)
	# frqs, a 1D numpy array of the frequencies associated with each frequency bin in dataF
	# dataF, a 1D numpy array (complex) of the FFT of the data at the particular sensor
	# Nu = slownesses.shape[0] (redundant but allows jit to work)
	# NTh = slowenesses.shape[1]
	# nFrq = frqs.size
	# 
	# OUTPUT:
	# RUpdate, a 3D numpy array (# of slownesses, # of angles, number of frequencies) 
	#	representing the contribution of this sensor to the whole array's R factor.




	timeLags = slownesses[:,:,0]*thisLoc[0] + slownesses[:,:,1]*thisLoc[1] # no. of slownesses x no of angles (u dot x-x_c)
	timeLagsFrqs = np.zeros((Nu,NTh,nFrq))
	for iu in range(Nu): # loop over slownesses
		for ith in range(NTh): # loop over angles
			timeLagsFrqs[iu,ith,:] = timeLags[iu,ith]*frqs
	# timeLagsFrqs should be no. of slownesses x no of angles x nFrq
	shifts = np.exp(-2*np.pi*1j*timeLagsFrqs) # no. of slownesses x no of angles x nFrq
	RUpdate = np.multiply(shifts,dataF) # phase shift of rrquency domain data and stack
	return RUpdate


def phase1(stations,frqs,nTrunc,locations,slownesses,funcToGenerateFilenames,startWindow):
	# This calculates the R factor for one array patch for a given time window.
	#
	# INPUTS:
	# stations, a list of station names (often this is a 4 letter/digit code)
	# frqs, a 1D numpy array of the frequencies associated with each 
	#	frequency bin in dataF 
	# nTrunc, number of entries to use for FFT (nearest power of 2 below 
	#	number of time samples)
	# locations, a 2D numpy array (# of sensors in array, 2) where each 
	#	row contains the x,y location (in meters) of a sensor
	# slownesses, a 3D numpy array with slownesses of interests 
	#	(# of slownesses, # of angles, 2) where 
	#	slownesses[iu,ith,0] = u*cos(theta) 
	#	and slownesses[iu,ith,1] = u*sin(theta)
	# funcToGenerateFilenames, a function that takes two arguments 
	#	(station name, a starting time described by obspy UTCTime object)
	#	to generate filename for each sensor (to be read w/ obspy.read())
	# startWindow, obspy UTCTime representing the starting time of this 
	#	window of data (for generating file name)
	# 
	# OUTPUTS: 
	# R, a 3D numpy array (# of slownesses, # of angles, number of frequencies) 
	#	representing the whole array's R factor for this time window

	# check dimensions of inputs
	Nu = slownesses.shape[0]
	NTh = slownesses.shape[1]
	nFrq = frqs.size

	R = np.zeros((Nu,NTh,nFrq))  # will store shifted 
	startTime = time.time()
	### Note: potential for easy parallelism over stations in this for loop (note: need reduce onto R) #######
	for i, station in enumerate(stations): 
	 	print('\t at station '+station+ ' and time '+str(time.time()-startTime))
	 	filename = funcToGenerateFilenames(station,startWindow)
	 	st = obspy.read(filename)
	 	# fourier transform of data (truncated to be power of 2)
	 	dataF = ft.fft(st[0].data,nTrunc) # not supported by numba jit currently
	 	# create array of shift factors 
	 	RUpdate = shiftFrqData(locations[i,:],slownesses,frqs,dataF,Nu,NTh,nFrq)
	 	R = R + RUpdate
	return R/len(stations)


def phase2(RA,RB,Nt):
	# Calculate the double beamforming transform for one window given R factors for 
	# the A and B arrays.
	#
	# INPUTS:
	# RA, 3D numpy array (NuA,NThA,number of frequencies), R factor for A 
	#	array in this time window
	# RB, 3D numpy array (NuB,NThB,number of frequencies), R factor for B 
	#	array in this time window
	# Nt, integer number of time lags of interest in the double beamforming transform
	#
	# OUTPUTS:
	# BTemp, a 5D numpy array (NuA,NThA,NuB,NThB,Nt) that describes the double 
	#	beamforming transform for this time window

	# check dimensions of RA and RB factors
	NuA = RA.shape[0] # number of slownesses array A
	NThA = RA.shape[1] # number of angles array A
	NuB = RB.shape[0] # number of slownesses array B
	NThB = RB.shape[1] # number of angles array B


	BTemp = np.zeros((NuA,NThA,NuB,NThB,Nt))
	startTime = time.time()
	###### Note: potential for easy parallelism over outermost for loop here, would correspondingly split up BTemp and RA along outermost axis (iuA) #######
	for iuA in range(NuA):
		print('\t iuA '+str(iuA)+' of '+str(NuA)+' and time '+str(time.time()-startTime))
		for iThA in range(NThA):
			print('\t \t iThA '+str(iThA))
			ThisRASection = RA[iuA,iThA,:]
			ThisRABTemp = np.zeros((NuB,NThB,Nt))
			for iuB in range(NuB):
				for iThB in range(NThB):
					ThisBFrqTemp =  np.multiply(ThisRASection,np.conj(RB[iuB,iThB,:]))
					ThisBTimeTemp = np.real(ft.ifft(ThisBFrqTemp)) # not supported by numba jit currently
					ThisRABTemp[iuB,iThB,:] = np.hstack((ThisBTimeTemp[-int(Nt/2):],ThisBTimeTemp[:int(Nt/2)]))
			BTemp[iuA,iThA,:,:,:] = ThisRABTemp
	return BTemp