"""
Usage:
    zot kmerize [-esm MEM] <k> <output> <input>...

Kmerize FASTA or FASTQ inputs to produce either a k-mer set or a k-mer
frequency set. If neither -e nor -s are given, a k-mer frequency set
is generated.

Arguments:
    <k>         the length of the k-mers. Recommended values: 10-30
    <output>    the name of the output file.
                recommended naming convention
                    - mykmers.k25 for a k-mer set of 25-mers
                    - mykmers.kf25 for a k-mer frequency set of 25-mers
                    - mykmers.e25 for an expanded k-mer set of 25-mers

Options:
    -s          generate a k-mer set
    -e          generate an expanded k-mer set
    -m MEM      in-memory buffer size
"""

from pykmer.basics import kmers
from pykmer.file import readFasta, readFastq
import pykmer.kset as kset
import pykmer.kfset as kfset

from merge import merge1, merge2

import docopt
import array
import gzip
import os
import sys

class KmerAccumulator:
    def __init__(self):
        self.toc = {}
        self.z = 0

    def __len__(self):
        return self.z

    def clear(self):
        self.toc = {}
        self.z = 0

    def add(self, x):
        xh = x >> 32
        xl = x & 0xFFFFFFFF
        if xh not in self.toc:
            self.toc[xh] = array.array('I')
        self.toc[xh].append(xl)
        self.z += 1

    def kmers(self):
        xhs = self.toc.keys()
        xhs.sort()
        for xh in xhs:
            x0 = xh << 32
            xls = self.toc[xh].tolist()
            xls.sort()
            for xl in xls:
                x = x0 | xl
                yield x

def openFile(fn):
    if fn == "-":
        return sys.stdin
    if fn.endswith(".gz"):
        return gzip.open(fn)
    return open(fn, 'rb')

def stripCompressionSuffix(nm):
    if nm.endswith('.gz'):
        return nm[:-3]
    return nm

def isFasta(nm):
    bnm = stripCompressionSuffix(nm)
    if bnm.endswith(".fa"):
        return True
    if bnm.endswith(".fasta"):
        return True
    if bnm.endswith(".fas"):
        return True
    if bnm.endswith(".fna"):
        return True

def mkParser(fn):
    if isFasta(fn):
        for (nm, seq) in readFasta(openFile(fn)):
            yield (nm, seq)
    else:
        for grp in readFastq(openFile(fn)):
            yield (grp[0], grp[1])

def mkPairs(xs):
    p = 0
    n = 0
    for x in xs:
        if x != p:
            if n > 0:
                yield (p, n)
            p = x
            n = 0
        n += 1
    if n > 0:
        yield (p, n)

def mkSet(xs):
    p = 0
    n = 0
    for x in xs:
        if x != p:
            if n > 0:
                yield p
            p = x
            n = 0
        n += 1
    if n > 0:
        yield p

def main(argv):
    opts = docopt.docopt(__doc__, argv)

    K = int(opts['<k>'])
    out = opts['<output>']
    s = opts['-s']
    Z = 1024*1024*32
    if opts['-m'] is not None:
        Z = 1024*1024*int(opts['-m'])
    buf = KmerAccumulator()
    n = 0
    tmps = []
    acgt = [0, 0, 0, 0]
    m = 0
    for fn in opts['<input>']:
        for (nm, seq) in mkParser(fn):
            for x in kmers(K, seq, True):
                buf.add(x)
                acgt[x&3] += 1
                m += 1
                n += 1
            if n >= Z:
                fn = 'tmps-%d.k%s%d' % (len(tmps), ('' if s else 'f'), K)
                tmps.append(fn)
                if s:
                    kset.write(K, mkSet(buf.kmers()), fn)
                else:
                    kfset.write(K, mkPairs(buf.kmers()), fn)
                buf.clear()
                n = 0

    if len(tmps):
        if len(buf):
            fn = 'tmps-%d.k%s%d' % (len(tmps), ('' if s else 'f'), K)
            tmps.append(fn)
            if s:
                kset.write(K, mkSet(buf.kmers()), fn)
            else:
                kfset.write(K, mkPairs(buf.kmers()), fn)
            buf = []

        zs = None
        if s:
            for fn in tmps:
                (_, xs) = kset.read(fn)
                if zs is None:
                    zs = xs
                else:
                    zs = merge1(K, zs, xs)
        else:
            for fn in tmps:
                (_, xs) = kfset.read(fn)
                if zs is None:
                    zs = xs
                else:
                    zs = merge2(K, zs, xs)
    else:
        if s:
            zs = mkSet(buf.kmers())
        else:
            zs = mkPairs(buf.kmers())

    n = float(sum(acgt))
    acgt = tuple([c/n for c in acgt])

    meta = {
        'total' : m,
        'distinct' : len(buf),
        'acgt' : acgt
    }

    if s:
        kset.write(K, zs, out, meta)
    else:
        kfset.write(K, zs, out, meta)

    for fn in tmps:
        os.remove(fn)