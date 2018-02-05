
import glob
try:
    from ..features.bwa_tools import get_seq
    from ..features.extract_events import get_raw, extract_events
except:
    from features.bwa_tools import get_seq
    from features.extract_events import get_raw, extract_events
import h5py
import numpy as np
from Bio import pairwise2
import pylab
import subprocess
import pandas as pd
import tempfile
import os


class NotAllign(Exception):

    def __init__(self, delta):
        self.message = "Delta = % i" % delta

REF = "data/external/ref/S288C_reference_sequence_R64-2-1_20150113.fa"


class Dataset:

    def __init__(self, samfile, root_files, metadata=""):
        self.root_files = root_files
        self.samfile = samfile
        self.metadata = ""

    def populate(self, maxf=None, minion=True, basecall=True,
                 filter_not_alligned=False, filter_ch=None, realign=False):
        self.strands = []
        lstrand = glob.glob(self.root_files + "/*")

        def find_strand(strand):
            for st in lstrand:
                if strand in st:
                    return st

        with open(self.samfile, "r") as f:
            for line in f.readlines():
                if maxf is not None and len(self.strands) >= maxf:
                    break
                sp = line.split()
                if len(sp) > 1 and sp[0].startswith("@ch"):
                    # print(sp[:4])
                    if "chr" in sp[2]:
                        X = int(sp[2][3:])
                    else:
                        X = 0

                    fn = "read_%s_ch_%s_" % (sp[0].split("_")[1][4:], sp[0].split("_")[0][3:])
                    # print(fn)
                    # print(find_strand(fn))

                    if filter_ch is not None and X not in filter_ch:
                        print("Skip in ch %i " % X)
                        continue

                    self.strands.append(Strand(find_strand(fn),
                                               X_from_Minion=int(X),
                                               t_from_Minion=0,
                                               sam_line_minion=line))

                    if basecall:
                        try:
                            self.strands[-1].signal_bc, self.strands[-1].seq_from_basecall, self.strands[-1].imin,
                            self.strands[-1].raw, self.strands[-1].to_match, self.strands[
                                -1].sampling_rate = self.strands[-1].get_seq(f="BaseCall")
                        except NotAllign:
                            print("Strand %i raw not alligned to basecall" % len(self.strands))

                            if filter_not_alligned:
                                print("Removed")
                                self.strands.pop(-1)
                    if minion:
                        if realign:
                            self.strands[-1].seq_from_minion = self.strands[-1].get_ref(
                                self.strands[-1].seq_from_basecall, correct=True)
                        else:
                            self.strands[-1].seq_from_minion = self.strands[-1].get_seq(
                                f="Minion", correct=True)

            """
            chp = kp.split("_")[0][3:]
            readp =  kp.split("_")[1][4:]
"""

"""
def compare_metrichor(file_netw,type_b="B",show_identical=False,ntwk=None):

    if type_b == "T":
        contrl = "BTF_AG_ONT_1_FAH14273_A-select.sam"
    if type_b == "B":
        contrl = "BTF_AH_ONT_1_FAH14319_A-select.sam"
    if type_b == "L":
        contrl = "BTF_AI_ONT_1_FAH14242_A-select.sam"
    if type_b == "E":
        contrl = "BTF_AK_ONT_1_FAH14211_A-select.sam"
    if type_b == "I":
        contrl = "BTF_AL_ONT_1_FAH14352_A-select.sam"

    with open(file_netw +"/"+ contrl.replace("select","select_pass_test_T"),"r") as f:
        datan = {}
        for line in f.readlines():
            sp = line.split()

            if len(sp) > 1 and sp[0].startswith("data"):
                datan[sp[0].split("/")[-1]] = sp[1:4]
            else:
                pass
                # print(sp)

"""


class Strand:

    def __init__(self, filename, X_from_Minion=0, t_from_Minion=0, sam_line_minion=""):
        self.filename = filename
        self.X_from_Minion = X_from_Minion
        self.t_from_Minion = t_from_Minion
        self.sam_line_minion = sam_line_minion

    def get_seq(self, f, correct=False):
        if f == "Minion":
            seq, sucess = get_seq(self.sam_line_minion, ref=REF, from_line=True, correct=correct)
            self.seq_from_minion = seq
            return self.seq_from_minion

        if f == "BaseCall":
            h5 = h5py.File(self.filename, "r")
            e2bis = h5["Analyses/Basecall_1D_000/BaseCalled_template/Events"]

            s2 = ""
            self.signal_bc = []
            left = None
            for ie, (s, length, m, ms, move, stdv) in enumerate(zip(e2bis["start"], e2bis["length"],
                                                                    e2bis["mean"], e2bis["model_state"], e2bis["move"], e2bis["stdv"])):

                state = "%s" % ms.tostring()
                state = state[2:-1]  # to remove b' and '
                # print(s)
                # state = state[2]

                if move == 1:
                    s2 += state[2]
                    state = state[2]
                    self.signal_bc.append([state, m, stdv, length, s])
                    left = None
                elif move >= 2:
                    s2 += state[1:3]
                    state = state[1:3]

                    if self.signal_bc[-1][0] == "N":
                        self.signal_bc[-1][0] = state[0]
                        self.signal_bc.append([state[1], m, stdv, length, s])
                    else:
                        self.signal_bc.append([state[0], m, stdv, length, s])
                        left = state[1]
                elif move == 0:
                    self.signal_bc.append(["N", m, stdv, length, s])
                    if left is not None:
                        self.signal_bc[-1][0] = left
                    left = None
                else:
                    left = None

            names = ["seq", "mean", "stdv", "length", "start"]
            self.signal_bc = pd.DataFrame({n: v for n, v in zip(
                names, np.array(self.signal_bc).T)}).convert_objects(convert_numeric=True)

            self.allign_basecall_raw()
            # print(self.signal_bc)

            self.signal_bc["start"] += (self.imin / self.sampling_rate - self.signal_bc["start"][0])

            self.seq_from_basecall = s2

            return self.signal_bc, self.seq_from_basecall, self.imin, self.raw, self.to_match, self.sampling_rate

    def score_ref(self, maxlen=1000):
        s1 = self.seq_from_minion
        s2 = self.seq_from_basecall
        self.score(s1, s2, maxlen=maxlen)

    def get_ref(self, sequence, correct=False):

        h, name = tempfile.mkstemp(prefix="", dir="./")
        os.close(h)
        with open(name + ".fasta", "w") as output_file:
            filename = "tmp"
            output_file.writelines(">%s_template_deepnano\n" % filename)
            output_file.writelines(sequence.replace("B", "T") + "\n")

        # try to add some prefix to the ref:
        if not os.path.exists(REF):
            if os.path.exists("../../" + REF):
                pre = "../../"
            else:
                print(REF, "not found")
        else:
            pre = ""
        exex = "bwa mem -x ont2d  %s  %s.fasta > %s.sam" % (pre + REF, name, name)
        try:
            subprocess.check_output(exex, shell=True, stderr=subprocess.STDOUT, close_fds=True)
        except subprocess.CalledProcessError as e:
            print(e.output)
            print(exex)
        ref, succes, X1, P1 = get_seq("%s.sam" % name, ref=pre + REF, ret_pos=True, correct=correct)
        # print(X1, P1)
        os.remove("%s.sam" % name)
        os.remove("%s.fasta" % name)
        os.remove(name)
        return ref

    def score(self, s1, s2, maxlen=None, all_info=False):

        if s1 == "":
            return None
        if s2 == "":
            return None

        if maxlen is not None:
            s1 = s1[:maxlen]
            s2 = s2[:maxlen]

        al = pairwise2.align.globalxs(s1, s2, -0.5, -0.5, one_alignment_only=True)[0]

        if all_info:
            return al
        else:
            return al[2] / len(s1)

    def allign_basecall_raw(self):

        h5 = h5py.File(self.filename, "r")
        raw, amp = get_raw(h5)

        e2bis = h5["Analyses/Basecall_1D_000/BaseCalled_template/Events"]
        to_match = np.zeros(int((e2bis["length"][-1] + e2bis["start"]
                                 [-1] - e2bis["start"][0]) * amp)) * np.nan

        s0 = e2bis["start"][0]

        for ie, (s, l, m) in enumerate(zip(e2bis["start"], e2bis["length"], e2bis["mean"])):
            to_match[int((s - s0) * amp):int(((s + l - s0) * amp))] = m

        mini = 100000
        lmatch = len(to_match)
        imin = 0
        for i in range(len(raw) - lmatch)[:5000]:
            delta = np.nanmean((raw[i:i + lmatch] - to_match)**2)
            if delta < mini:
                imin = i + 0
                mini = delta + 0
                # print(delta)

        if mini > 100:
            raise NotAllign(mini)
        # print(delta,imin)
        self.imin = imin
        self.to_match = np.array(to_match, dtype=np.float16)
        self.raw = np.array(raw, dtype=np.float16)
        self.sampling_rate = amp

    def get_seq_mean(self, motif, ref, short=True, void="N", caract="mean"):

        seq = "".join(ref["seq"].replace(void, ""))
        if motif in seq:
            num = [i for i, l in(enumerate(ref["seq"])) if l != void]
            index = seq.index(motif)
            if short:
                return motif, np.array(ref[caract][num[index:index + len(motif)]])
            else:
                return motif, np.array(ref[caract][num[index]:num[index + len(motif)]])
        else:
            return motif, None

    def give_map(self, ref, allgn):
        """
        given a ref from basecall or network, and an allignment with
        the true sequence, return a new ref, matching more closely
        the true sequence
        """
        indexes = [i for i, l in enumerate(ref) if l != "N"]
        # print(indexes)
        i = 0
        alb = []
        for l in allgn[0]:
            if l != "-":
                alb.append(indexes[i])
                i += 1
            else:

                # if in alb there are "-" which are surrounded by non adjacent integer we
                # can add insert letters:
                if alb != [] and type(alb[-1]) == int and i < len(indexes) and indexes[i] - 1 > alb[-1]:
                    alb.append(alb[-1] + 1)
                else:
                    alb.append("-")

        """print(allgn[0])
        print("".join(map(str, alb)))
        print(allgn[1])"""

        # Look for numeric which correspend to "-" to see if we can insert more of the sequence
        # Look for diagonal pattern of "-"
        switch = []
        for ind, (num, nump, l, lp) in enumerate(zip(alb[:-1], alb[1:], allgn[1][:-1], allgn[1][1:])):

            if (num == "-" and lp == "-") or (nump == "-" and l == "-"):
                switch.append(ind)
        # print(switch)
        for ind in switch:
            alb[ind], alb[ind + 1] = alb[ind + 1], alb[ind]

        mapped = ["N" for l in ref]
        for num, l in zip(alb, allgn[1]):
            if type(num) == int:
                if l != "-":
                    mapped[num] = l

        correction = ["N" for l in ref]
        for ind, (num, nump, l, lp) in enumerate(zip(alb[:-1], alb[1:], allgn[1][:-1], allgn[1][1:])):

            if num != "-" and nump == "-" and lp != "-":
                correction[num] = lp

        return "".join(mapped), "".join(correction)

    def show_segmentation_bc(self):
        self.allign_basecall_raw()
        #l = len(self.to_match)

        #pylab.plot(self.raw[:l + self.imin])
        pylab.plot(self.raw)

        pylab.plot(*self.segmentation_to_plot(self.signal_bc, shift=self.imin))

    def segmentation_to_plot(self, sign, shift=None, sl=6024):
        X = []
        Y = []
        s0 = 0
        if shift is not None:
            s0 = sign["start"][0]
        else:
            shift = 0
        for i, (s, l, m) in enumerate(zip(sign["start"], sign["length"], sign["mean"])):
            X += [(s - s0) * sl + shift, (s - s0 + l) * sl + shift]
            Y += [m, m]

        return np.array(X), np.array(Y)

    def plot_sequence(self, sign, window=[None, None], color="k", up=5):
        sl = self.sampling_rate
        for i, (s, l, m, base) in enumerate(zip(sign["start"], sign["length"], sign["mean"], sign["seq"])):

            if (window[0] is None or (window[0] is not None and s * sl > window[0])) and \
                    (window[1] is None or (window[1] is not None and s * sl < window[1])):
                pylab.text((s + l / 2) * sl - 1.5, m + up, base,
                           color=color)  # 1.5 size of character

    def segmentation(self, chem="rf", w=5, prefix=""):
        h5 = h5py.File(prefix + self.filename, "r")
        self.segments = extract_events(h5, chem="rf", window_size=w, old=False)

    def analyse_segmentation(self, ntwk, signal):

        pre = ntwk.predict(signal[np.newaxis, ::, ::])[0]
        n = pre.shape[-1]
        # print(n)
        if n == 4 + 1:
            alph = "ACGTN"
        if n == 5 + 1:
            alph = "ACGTBN"
        if n == 8 + 1:
            alph = "ACGTBLEIN"

        b = np.argmax(pre, axis=-1)
        output = np.array(list(map(lambda x: str(alph)[x], b)))[::, np.newaxis]
        return np.concatenate((output, signal), axis=-1)

    def transfer(self, root_signal, signal_to_label, center_of_mass=False):
        # Compute center:

        r_center = root_signal["start"] + root_signal["length"] / 2
        stl_center = signal_to_label["start"] + signal_to_label["length"] / 2

        stl_base = []

        if center_of_mass:

            for c in stl_center:
                where = np.argmin(np.abs(r_center - c))
                stl_base.append(root_signal["seq"][where])

        else:
            # Force assignation of bases
            stl_base = ["N" for i in range(len(signal_to_label))]
            for ib, b in enumerate(root_signal["seq"]):
                if b != "N":

                    s = (r_center[ib] > signal_to_label["start"]) &  \
                        (r_center[ib] < (signal_to_label["start"] + signal_to_label["length"]))

                    # where = np.argmin( np.abs(stl_center-r_center[ib]))
                    where = np.argmax(s)
                    stl_base[where] = b

        new_signal = []
        for s, m, std, l, start in zip(stl_base, signal_to_label["mean"], signal_to_label["stdv"],
                                       signal_to_label["length"], signal_to_label["start"]):
            new_signal.append([s, m, std, l, start])

        names = ["seq", "mean", "stdv", "length", "start"]
        return pd.DataFrame({n: v for n, v in zip(
            names, np.array(new_signal).T)}).convert_objects(convert_numeric=True)

"""
ref = "../../data/processed/results/ctc_20170908-R9.5/BTF_AG_ONT_1_FAH14273_A-select_pass_test_T.sam"
new = "../../data/processed/results/v9p5-new_ctc_20170908-R9.5/BTF_AG_ONT_1_FAH14273_A-select_pass_test_T.sam"
root = "../../data/raw/20170908-R9.5/"
D = Dataset(samfile = root + "BTF_AG_ONT_1_FAH14273_A-select.sam",
            root_files=root+"AG-basecalled/")
D.populate(maxf=10,filter_not_alligned=True,filter_ch =range(1,11) )
s = D.strands[0]"""