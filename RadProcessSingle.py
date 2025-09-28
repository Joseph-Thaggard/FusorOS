import csv
import os
import matplotlib.pyplot as plot
import numpy as np
import pandas as pd

### Path for file
Path_VAR = '/Users/joe/Desktop/RadData/Pulse1/Test1.csv'
###

### Useful variables
x = [0]
y = [0]
dy = [0]
i = l = n = 0

### Read CSV and store to vector
with open(Path_VAR) as csvfile:
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
max = max(dy)
val = np.zeros(int(max)+1)
idx = np.zeros(int(max+1))
for n in range(len(dy)):
    m = int(dy[n])
    #print(m)
    val[m] = val[m]+1
for p in range(len(val)):
    idx[p] = p
    #print(idx[p])

### Print Clean Figure
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

