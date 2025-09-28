import csv
import os
import matplotlib.pyplot as plot
import numpy as np
import pandas as pd

### Path for folder
Path_List = '/Users/joe/Desktop/RadData/Pulse1'
###

all=os.listdir(Path_List)
Path_VAR = []
for entry in all:
    # Check for files
    full=os.path.join(Path_List,entry)
    # Add to list if .csv
    if os.path.isfile(full) and entry.endswith(".csv"):
        Path_VAR.append(entry)

### Batch Storage
batchidx = []
batch = []
histidx = []
hist = []

### Bool Settings
yesplot = True
###

### Read CSV and store to vector
for var in range(len(Path_VAR)):
    ### Useful variables
    x = [0]
    y = [0]
    dy = [0]
    i = l = n = 0
    print(os.path.join(Path_List,Path_VAR[var]))
    with open(os.path.join(Path_List,Path_VAR[var])) as csvfile:
        read = csv.reader(csvfile, delimiter=',')
        for row in read:
            if i >= 1:
                # Grab row values
                a = int(row[0])
                b = int(row[1])
                # Set iteration count to skip first row
                i = i-1
                if i == 0:
                    x[i] = a
                    y[i] = b
                if i > 0:
                    x.append(a)
                    y.append(b)
                # Restore iteration count
                i = i+1
            # Forward iteration count
            i += 1
    ###    

    ### Identifying Jumps 
    for l in range(len(x)-1):
        #Single-step derivative
        c = (y[l]-y[l+1])/(x[l]-x[l+1])
        if c > 0:
            dy.append(c)
        #If clean and only accept positive values
        if c <= 0:
            dy.append(0)

    ### Histogram Sort
    maxdy = max(dy)
    val = np.zeros(int(maxdy)+1)
    idx = np.zeros(int(maxdy)+1)
    for n in range(len(dy)):
        m = int(dy[n])
        #print(m)
        val[m] = val[m]+1
    for p in range(len(val)):
        idx[p] = p
        #print(idx[p])
    batchidx.append(idx)
    batch.append(val)
    
    ### Print Clean Figure
    if yesplot == True:
        fig, ax = plot.subplots(3, sharex=False, sharey=False)
        fig.suptitle('Radiation Recorder Data')
        ax[0].set_ylim(0,255)
        ax[0].set_xlim(0,10000)
        ax[0].plot(x,y)
        ax[0].plot(x,dy)
        ax[1].hist(dy, bins=10000, log=True)
        ax[1].set_xlim(1,255)
        ax[2].plot(idx,val)
        ax[2].set_xlim(2,255)
        plot.show()

### Compiling Batch Hisogram
idxlen = []
histlen = []
t = g = 0
# Fixing length of full indexes to longest entry
for u in range(len(batchidx)):
    idxlen.append(len(batchidx[u]))
    histlen.append(len(batch[u]))
#print(max(idxlen))
#print(max(histlen))
pos = idxlen.index(max(idxlen))
#print(pos)
histidx = np.zeros(max(idxlen))
hist = np.zeros(max(histlen))
# Build idx first based on largest index in the batch
for r in range(len(batchidx[pos])):
    histidx[t] = batchidx[pos][r]
    #print(histidx[m])
# Combining lists
for o in range(len(batchidx)): 
    # Build histogram by compiling on existing points
    for w in range(len(batch[o])):
        #print(int(batch[o][w]))
        #print(hist[w])
        hist[w] = hist[w] + int(batch[o][w])
        #print(hist[w])


plot.plot(hist)
plot.xlim(1,255)
plot.yscale('log')
#plot.ylim(0,300)
plot.show()