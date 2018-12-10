import argparse
from .simple_utilities import load_data, load_events, transform_reads
from keras.models import Sequential
from keras.layers import Dense, Flatten, TimeDistributed, AveragePooling1D
from keras.layers import LSTM
from keras.layers.convolutional import Conv1D
from keras.layers.convolutional import MaxPooling1D
import numpy as np
import pylab
import pandas as pd
import os


def model(typem=1, base=False):
    init = 1
    if base:
        init = 5
    if typem == 1:

        model = Sequential()
        # model.add(Embedding(top_words, embedding_vecor_length, input_length=max_review_length))
        model.add(Conv1D(filters=32, kernel_size=3, padding='same',
                         activation='relu', input_shape=(200, init)))
        model.add(MaxPooling1D(pool_size=2))
        model.add(LSTM(100))
        model.add(Dense(1, activation='linear'))
        model.compile(loss='mse', optimizer='adam')  # , metrics=['accuracy'])
        ntwk = model
    if typem == 7:
        model = Sequential()
        # model.add(Embedding(top_words, embedding_vecor_length, input_length=max_review_length))
        model.add(Conv1D(filters=32, kernel_size=5, padding='same',
                         activation='relu', input_shape=(96, init)))
        """
        model.add(MaxPooling1D(pool_size=4)) # 16
        model.add(Conv1D(filters=64, kernel_size=5, padding='same',
                         activation='relu'))
        model.add(MaxPooling1D(pool_size=4)) #4
        model.add(Conv1D(filters=64, kernel_size=5, padding='same',
                                 activation='relu'))

        #model.add(LSTM(100))
        #model.add(Dense(1, activation='linear'))
        """
        model.add(MaxPooling1D(pool_size=4))
        model.add(Conv1D(filters=32, kernel_size=5, padding='same',
                         activation='relu'))
        model.add(MaxPooling1D(pool_size=4))
        model.add(Conv1D(filters=32, kernel_size=5, padding='same',
                         activation='relu'))
        model.add(TimeDistributed(Dense(1, activation='sigmoid')))
        model.add(AveragePooling1D(pool_size=6))
        model.add(Flatten())
        ntwk = model
        lenv = 96
    ntwk.summary()
    return ntwk


parser = argparse.ArgumentParser()

parser.add_argument('--file', dest='filename', type=str)
parser.add_argument('--extra', dest='extra', type=str, default="")
parser.add_argument('--root', dest='root', type=str,
                    default="/data/bioinfo@borvo/users/jarbona/deepnano5bases/data/raw/")
parser.add_argument('--weight-name', dest='weight_name', type=str)
parser.add_argument('--typem', dest='typem', type=int, default=1)
parser.add_argument('--thres', dest='thres', type=float, default=0.3)
parser.add_argument('--maxf', dest='maxf', type=int, default=None)
parser.add_argument('--window-length', dest='length_window', type=int, default=200)
parser.add_argument('--compute-only', dest="compute_only", action="store_true")
parser.add_argument('--base', dest="base", action="store_true")
parser.add_argument('--rescale', dest="rescale", action="store_true")

Tt = np.load("T-T1-corrected-transition.npy")

args = parser.parse_args()

filename = args.filename
length_window = args.length_window
maxf = args.maxf
weight_name = args.weight_name
typem = args.typem
extra = args.extra
root = args.root

if args.base:
    root = '/data/bioinfo@borvo/users/jarbona/deepnano5bases/data/tomb/clean_name/'

X, y = load_data([filename], root=root)
if not args.base:
    Xr, yr, fn = load_events(X, y, min_length=length_window, base=args.base, maxf=args.maxf)
    extra_e = []
else:
    Xr, yr, fn, extra_e = load_events(X, y, min_length=length_window,
                                      base=args.base, maxf=args.maxf, extra=True)
assert(len(fn) == len(Xr))
print("Nfiles", len(Xr))
yr = np.array(yr)
Xt, yt, which_keep = transform_reads(
    Xr, yr, lenv=length_window, Tt=Tt, rescale=args.rescale, extra_e=extra_e)

fn = [ifn for ifn, w in zip(fn, which_keep) if w]

ntwk = model(typem=typem, base=args.base)
ntwk.load_weights(weight_name)

Predicts = []
for xt in Xt:
    Predicts.append(np.mean(ntwk.predict(xt)))

fname = os.path.split(filename)[-1][:-4]
Predicts = np.array(Predicts)
pylab.hist(Predicts, bins=40)
fnf = weight_name[:-5]+"histo_B_T_%s" % (fname)+extra+".pdf"
print("Percent of reads < %.1f" % args.thres, np.sum(Predicts < args.thres)/len(Predicts))
pylab.savefig(fnf)
print("Writing", weight_name[:-5]+"histo_B_T_%s" % (fname)+extra+".pdf")
csvf = pd.read_csv(filename)
wn = weight_name[:-5]
csvf[wn] = [1 for _ in range(len(csvf))]
found = 0
assert len(Predicts) == len(fn)
for f, r in zip(fn, Predicts):
    if args.compute_only:
        b = r
    else:
        if r > args.thres:
            b = 1
        else:
            b = 0
    fnshort = f.replace(root, "")

    which = csvf["filename"] == fnshort
    found += np.sum(which)
    csvf.loc[which, wn] = b

print("Number processed", found)
csvf.to_csv(filename, index=False)
