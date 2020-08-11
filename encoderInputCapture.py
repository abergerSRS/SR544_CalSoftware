# -*- coding: utf-8 -*-
"""
Created on Wed Feb  5 14:20:07 2020

@author: aberger

This program imports four columns of data:
    1. enc raw count (0-99)
    2. input capture of shaft edges on "free running" 60 MHz FTM counter
    3. chop wheel raw count (0-99 for 100-slot outer track)
    4. input capture of chop edges on "free running" 60 MHz FTM counter
"""

import numpy as np
import matplotlib.pyplot as plt
from numpy import sqrt, pi, exp, linspace, random
import os

# custom modules
import fileWriter

plt.close('all')

#filename = r'D:\Documents\MCUXpressoIDE_10.1.0_589\workspace\SR544\tools\edgesAndCounts_80Hz_10100Blade_UVWconnected.txt'
filename = r'D:\Documents\MCUXpressoIDE_10.1.0_589\workspace\SR544\tools\edgesAndCounts_80Hz_10100Blade_UVWdisconnected.txt'
#filename = r'D:\Documents\MCUXpressoIDE_10.1.0_589\workspace\SR544\tools\edgesAndCounts_80Hz_10100Blade_innerTrackCal.txt'

# 400 count encoder
#filename = r'D:\Documents\MCUXpressoIDE_10.1.0_589\workspace\SR544\tools\edgesAndCounts_35Hz_10100Blade_400CountEnc_innerTrackCal.txt'
#filename = r'D:\Documents\MCUXpressoIDE_10.1.0_589\workspace\SR544\tools\edgesAndCounts_35Hz_HeavyBlades_400CountEnc_innerTrackCal.txt'

data = np.loadtxt(filename, delimiter=' ', usecols=[0,1,2,3], skiprows=0)

encCount = data[:,0]
encEdge = data[:,1]

N_samples = len(encCount)
N_enc = 100 #number of ticks on shaft encoder
f_FTM = 60e6 #Hz
FTM_MOD = 4096 #FTM_MOD for the FTM peripheral used to collect these data

dt = FTM_MOD/f_FTM
t = np.linspace(0, dt*N_samples, N_samples)
encoderCount = np.linspace(0, N_enc - 1, N_enc)


# TODO: finish building out this class to make the code more object-oriented
class RotaryEncoder():
    def __init__(self, N_ticks):
        self.N_ticks = N_ticks
        self.tickArray = np.linspace(0, self.N_ticks - 1, self.N_ticks)
        self.avgTickSpacing = np.zeros(len(N_ticks))
        self.tickCorrection = np.zeros(len(N_ticks))

# Given: integer counts, FTM input captured CnV values @ edges, time array
# Return: 
#1. integer count at edge corresponding to CnV_i, 
#2. delta = CnV_i - CnV_(i-1)
#3. t1 = time at edge corresponding to CnV_i
def measureCountDeltas(counts, edges, time, maxCount):
    rawCount = np.zeros(0)
    deltaCount = np.zeros(0)
    deltaFTM = np.zeros(0)
    t1 = np.zeros(0)
    for i, edge in enumerate(edges[1:], start=1):
        if edge != edges[i-1]:
            rawCount = np.append(rawCount, counts[i])
            deltaCount = np.append(deltaCount, (counts[i] - counts[i-1])%maxCount)
            t1 = np.append(t1, time[i])
            deltaFTM = np.append(deltaFTM, edge - edges[i-1])
            
    return rawCount, deltaCount, deltaFTM, t1

# Given: a 1-D array of data
# Returns: a sliding window average where the window for the i-th average
# is centered on the i-th point (so equally forward- and backward-looking)
def movingAverage(data, windowSize):
    avg = np.zeros(len(data))
    delta = int(np.floor(windowSize/2))
    
    for i in range(delta):
        avg[i] = data[i]
        
    for i in range(len(data) - delta, len(data)):
        avg[i] = data[i]
        
    for i, datum in enumerate(data[delta:-delta], start=delta):
        avg[i] = np.sum(data[i - delta: i + delta + 1])/(windowSize+1)
    
    return avg

def findIndexOfNearest(array, value):
    array = np.asarray(array)
    idx = (np.abs(array - value)).argmin()
    return idx

def findWrapArounds(array):
    wrapIndex = np.zeros(0, dtype='int')
    for i, val in enumerate(array):
        if val - array[i-1] < 0:
            wrapIndex = np.append(wrapIndex, i)
            
    return wrapIndex

# First, calculate the delta FTM counts
encCountAtDelta, encCountDelta, encFtmDelta, encTimeAtDelta = measureCountDeltas(encCount, encEdge, t, N_enc)

# This can be easily converted to delta t in seconds
encFtmDeltaT_sec = encFtmDelta/f_FTM

# Which can be converted to estimated speed as a function of time:
encSpeed = encCountDelta/(N_enc*encFtmDeltaT_sec)
        
# Calculate the moving average to smooth over the fine-scale variation due to 
# encoder errors (window size >= N_enc)
windowSize = int(5*N_enc/2)
avgEncSpeed = movingAverage(encSpeed, windowSize)

# Plot Speed vs Time
fig1, ax1 = plt.subplots()
ax1.plot(encTimeAtDelta[1:], encSpeed[1:])
ax1.plot(encTimeAtDelta[1:], avgEncSpeed[1:])
ax1.set_ylim(min(encSpeed[1:]), max(encSpeed[1:]))
ax1.set_xlabel('time (s)')
ax1.set_ylabel('speed (rev/s)')
ax1.set_title('Free Spindle Decay: speed vs. time')
ax1.legend(('shaft encoder', 'windowed average, N='+str(windowSize)))

# The main step of the calibration is to convert the delta t measurements
# to tick spacing (in revs). This requires a "perfect" estimator of the instanteous
# shaft speed 

# tick spacing calculated *without* circular closure constraint
encTickSpacing = avgEncSpeed*encFtmDeltaT_sec

# Find the average and stdev of tick spacing over N_revsToAvg revolutions
def CalculateAvgTickSpacing(N_ticks, N_revsToAvg, N_revsToWait, tickSpacing_revs, rawCountAtDelta):
    measTickSpacing = np.zeros((N_ticks, N_revsToAvg))
    indexOfZerothTick = np.where(rawCountAtDelta == 0)
    i = 0
    for index in indexOfZerothTick[0]:
        if i >= N_revsToAvg:
            break
        if index > N_revsToWait*N_ticks:
            #distFromZerothTick[k, i]:
            measTickSpacing[:,i] = (tickSpacing_revs[index:index+N_ticks])
            i += 1
    avgTickSpacing = np.mean(measTickSpacing, axis=1)
    stdTickSpacing = np.std(measTickSpacing, axis=1)
    
    return (avgTickSpacing, stdTickSpacing)

(avgTickSpacing, stdTickSpacing) = CalculateAvgTickSpacing(N_enc, 10, 3, encTickSpacing, encCountAtDelta)

# Use Least Squares with Circular Closure to determine tick spacing
# 1. Want to solve A*x = b, subject to least squares such that we minimize ||b - A*x||
# 2. In our case, A = I*(1/omega), with a final row of ones
# 3. x = encoder tick spacing, which we are solving for
# 4. b = measured Delta T's, with a final element of one
# 5. The augmented elements of A and b enforce circular closure such that:
# sum_i x_i = 1 (the sum of all tick spacings over one revolution should equal one revolution)
def LeastSquaresTickSpacing(N_ticks, N_revsToAvg, N_revsToWait, startCount, rawCountAtDelta, speed, deltaT):
    measTickSpacing = np.zeros((N_ticks, N_revsToAvg))
    indexOfZerothTick = np.where(rawCountAtDelta == startCount)
    i = 0
    for index in indexOfZerothTick[0]:
        if i >= N_revsToAvg:
            break
        if index > N_revsToWait*N_ticks:
            A = np.identity(N_ticks)*1/speed[index:index+N_ticks]
            A = np.append(A, np.ones((1, N_ticks)), axis=0)
            b = deltaT[index:index+N_ticks]
            b = np.append(b, 1)
            lstsqsol = np.linalg.lstsq(A, b)
            measTickSpacing[:,i] = lstsqsol[0]
            i += 1
            
    avgTickSpacing = np.mean(measTickSpacing, axis=1)
    stdTickSpacing = np.std(measTickSpacing, axis=1)
    
    return (np.roll(avgTickSpacing, startCount), stdTickSpacing)

(lsAvgTickSpacing, lsStdTickSpacing) = LeastSquaresTickSpacing(N_enc, 10, 3, 0, encCountAtDelta, avgEncSpeed, encFtmDeltaT_sec)
(lsAvgTickSpacing_start200, lsStdTickSpacing_start200) = LeastSquaresTickSpacing(N_enc, 10, 3, 200, encCountAtDelta, avgEncSpeed, encFtmDeltaT_sec)

fig2, ax2 = plt.subplots()
ax2.errorbar(encoderCount, avgTickSpacing, yerr=stdTickSpacing, marker='.', capsize=4.0, label='no circular closure', zorder=0)
ax2.errorbar(encoderCount, lsAvgTickSpacing, yerr=lsStdTickSpacing, marker='.', capsize=4.0, label='circular closure, start = 0', zorder=0)
ax2.plot(encoderCount, 1/N_enc*np.ones(N_enc), '--', label='ideal', zorder=1)
ax2.set_xlabel('encoder count')
ax2.set_ylabel(r'$\Delta \theta$ (revs)')
ax2.legend()
ax2.set_title('Tick Spacing, '+r'$\Delta \theta_i = \bar{f}_i*\Delta t_i$')
fig2.tight_layout()

tickSpacingRescale = 1/(N_enc*lsAvgTickSpacing)
fileWriter.saveDataWithHeader(os.path.basename(__file__), filename, tickSpacingRescale, 'float', '1.7f', 'tickRescale100')

# For N_revsToAvg worth of data, calculate the cumulative distance from tick 0 to tick k
def ConvertSpacingToCorrections(N_ticks, N_revsToAvg, N_revsToWait, tickSpacing_revs, rawCountAtDelta):
    distFromZerothTick_revs = np.zeros((N_ticks, N_revsToAvg))
    indexOfZerothTick = np.where(rawCountAtDelta == 0)
    i = 0
    for index in indexOfZerothTick[0]:
        if i >= N_revsToAvg:
            break
        if index > N_revsToWait*N_ticks:
            #distFromZerothTick[k, i]:
            distFromZerothTick_revs[:,i] = np.cumsum(tickSpacing_revs[index:index+N_ticks]) - 1/N_ticks
            i += 1
            
    # The tick correction is then simply the difference between the expected tick position
    # (encoderCount/N_enc) and the measured distFromZerothTick
    tickCorrection_revs = np.zeros((N_ticks, N_revsToAvg))
    encoderCount = np.linspace(0, N_ticks - 1, N_ticks)
    for i, col in enumerate(distFromZerothTick_revs.T):
        tickCorrection_revs[:,i] = encoderCount/N_ticks - col
        
    # Calculate the average and standard deviation of the tick corrections to check
    # for reproducibility
    avgTickCorrection = np.mean(tickCorrection_revs, axis=1)
    stdTickCorrection = np.std(tickCorrection_revs, axis=1)
    
    return (avgTickCorrection, stdTickCorrection)

def ConvertLSSpacingToCorrections(N_ticks, lsTickSpacing_revs):
    distFromZerothTick = np.cumsum(lsTickSpacing_revs) - 1/N_ticks
    
    encoderCount = np.linspace(0, N_ticks - 1, N_ticks)
    tickCorrection_revs = encoderCount/N_ticks - distFromZerothTick
    
    return tickCorrection_revs

# Tick Corrections *without* circular closure
(avgTickCorrection, stdTickCorrection) = ConvertSpacingToCorrections(N_enc, 10, 3, encTickSpacing, encCountAtDelta)

# Assume that the average tick correction over one cycle is zero (otherwise,
# there will be some angle-indepedent offset imparted by the tick correction)
offsetTickCorrection = np.mean(avgTickCorrection)
avgTickCorrection -= offsetTickCorrection

# Tick Corrections *with* circular closure
lsTickCorrection = ConvertLSSpacingToCorrections(N_enc, lsAvgTickSpacing)
lsTickCorrection_start200 = ConvertLSSpacingToCorrections(N_enc, lsAvgTickSpacing_start200)
lsOffset = np.mean(lsTickCorrection)
lsTickCorrection -= lsOffset

fig3, ax3 = plt.subplots()
ax3.plot(encoderCount/N_enc*360, lsTickCorrection, marker='.', label = 'circular closure, start = 0')
ax3.plot(encoderCount/N_enc*360, lsTickCorrection_start200 - np.mean(lsTickCorrection_start200), label = 'circular closure, start = 200')
#ax3.errorbar(encoderCount/N_enc*360, avgTickCorrection, yerr=stdTickCorrection, marker='.', capsize=4.0, label='no circular closure')
ax3.set_xlabel('rotor angle (deg)')
ax3.set_ylabel('tick error (mech. revs)')
ax3.set_title('Tick error, '+r'$\langle \theta_i \rangle - \theta_i = \frac{i}{N_{enc}} - \sum_{k=0}^i \Delta \theta_k$', y = 1.03)
ax3.legend()
fig3.tight_layout()

"""
Test the correction -----------------------------------------------------------
"""
# Use the average tick spacing to re-scale the speed measurements, 
# where the scaling factor is measTickSpacing/perfectTickSpacing
corrSpeed = encSpeed/tickSpacingRescale[encCountAtDelta.astype(int)]
ax1.plot(encTimeAtDelta[1:], corrSpeed[1:])
ax1.legend(('shaft encoder', 'windowed average, N='+str(windowSize), 'corrected encoder speed'))

fig4, ax4 = plt.subplots()
ax4.plot(encTimeAtDelta[1:], avgEncSpeed[1:] - encSpeed[1:])
ax4.plot(encTimeAtDelta[1:], avgEncSpeed[1:] - corrSpeed[1:])
ax4.legend(('original','corrected'))
ax4.set_xlabel('time (s)')
ax4.set_ylabel('speed error (revs/s)')
ax4.set_title('Speed error comparison')
fig4.tight_layout()

angleCorr_int32 = lsTickCorrection*2**32
#fileWriter.saveDataWithHeader(os.path.basename(__file__), filename, angleCorr_int32.astype(int), 'int32_t', 0, 'angleComp')