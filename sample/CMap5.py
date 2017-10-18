#!/usr/bin/env python

#####################################################
# Script for generating contact probability map     #
# Author: ZHENG Liangzhen                           #
# Email: LZHENG002@e.ntu.edu.sg                     #
# Version: V3.2                                    #
# Date: 15 June 2017                                 #
#####################################################

import glob
import math
import sys
import argparse
import os
import numpy as np
from collections import defaultdict
from argparse import RawTextHelpFormatter
from datetime import datetime
from mpi4py import  MPI

class ContactMap:
    def __init__(self, hugePDBFile) :
        self.mfPDB = hugePDBFile

    def extractReference(self):
        reference = self.mfPDB+"_reference.pdb"
        if not os.path.exists(reference) :
            with open(reference, 'wb') as tofile :
                with open(self.mfPDB) as lines :
                    for s in lines :
                        if s[:6].strip() in ["ATOM", "HETATM"] :
                            tofile.write(s)
                        elif s.split()[0] in ["END", "ENDMDL"] :
                            tofile.write(s)
                            break
        return reference

    def splitPdbFile(self):
        '''
        read a large pdb file to obtain the splitted files
        :return: a list of single-frame pdb file
        '''
        """
        This function split the large Multi-frame PDB file
        Only the atoms in the atomNdx will be written to seperated files
        """

        if 'S_1.pdb' in os.listdir('./') :
            filelist = glob.glob('S_*.pdb')

        else :
            filelist = []
            with open(self.mfPDB) as lines :
                for s in lines :
                    if "MODEL" == s.split()[0] :
                        no_model = s.split()[1]
                        tofile = open("S_"+no_model+".pdb",'wb')
                        filelist.append("S_"+no_model+".pdb")
                        tofile.write(s)
                    elif "ATOM" == s.split()[0] :
                        tofile.write(s)

                    elif "ENDMDL" in s :
                        tofile.write(s)

                        tofile.close()
                    else :
                        pass

        print "PDB File spliting finished! \n"
        return (sorted(filelist))

    def switchFuction(self, x, d0, m=12, n=6):
        '''
        a switch function is a way to make the counting continuous
        :param x: distance
        :param d0: cutoff
        :param m:
        :param n:
        :return: a switched distance
        '''
        # for countting, implement a rational switch function to enable a smooth transition
        # the function is lik  s= [1 - (x/d0)^6] / [1 - (x/d0)^12]
        # d0 is a cutoff
        count = 0.0
        try :
            count = (1.0 - math.pow((x / d0), n)) / (1.0 - math.pow((x / d0), m))
        except ZeroDivisionError :
            print "Divide by zero, ", x, d0

        return count


    def getResIndex(self, singleFramePDB, chain, resIdList):
        ## get the index of the residues from the pdbfile
        indexlist = []
        with open(singleFramePDB) as lines :
            indexlist = [ s[22:28].strip() + '_' + chain
                          for s in lines
                          if "ATOM" in s and s[21] == chain and
                          int(s[22:26].strip()) in resIdList and
                          s[22:28].strip() + '_' + chain not in indexlist
                          ]

            '''for s in lines:
                if "ATOM" in s and s[21] == chain and int(s[22:26].strip()) in resIdList:
                    resIndex = s[22:28].strip() + '_' + chain
                    if resIndex not in indexlist:
                        indexlist.append(resIndex) '''
        return indexlist

    def withSubGroup(self, isProtein=True, nucleic="nucleic-acid.lib"):
        if isProtein :
            subgroup = {}
            for atom in ['CA', 'N', 'C', 'O'] :
                subgroup[atom] = "mainchain"
            for atom in ['CZ2', 'OE2', 'OE1', 'OG1', 'CD1', 'CD2', 'CG2', 'NE', 'NZ', 'OD1',
                         'ND1', 'ND2', 'OD2','CB', 'CZ3', 'CG',  'CZ',
                         'NH1', 'CE', 'CE1', 'NH2', 'CG1', 'CD', 'OH', 'OG', 'SG', 'CH2',
                         'NE1', 'CE3', 'SD', 'NE2', 'CE2'] :
                subgroup[atom] = 'sidechain'

            return subgroup
        else :
            xna = {}
            if os.path.exists(nucleic) :
                with open(nucleic) as lines :

                    for s in lines :
                        if "#" not in s :
                            xna[s.split()[-1]] = s.split()[1]

            return xna

    def atomInformation(self, pdbin, proteinres="amino-acid.lib"):
        # elements in atom infor
        # key: atom index
        # value: [atomname, molecule type, is_hydrogen,  resname, resndx, chainid,(mainchian, sidechain,
        #           sugar ring, phosphate group, base ring)]
        atominfor = defaultdict(list)

        protRes = []
        with open(proteinres) as lines :
            protRes = [ s.split()[2] for s in lines if "#" not in s ]
        DNARes = ['DA','DT','DC','DG']
        RNARes = ['A','G','C','U']

        prosubgroup = self.withSubGroup(True)
        xnasubgroup = self.withSubGroup(False)

        with open(pdbin) as lines :
            for s in lines :
                if len(s.split()) and s[:4] in ["ATOM", "HETA"] :

                    atomndx = s[6:11].strip()
                    atomname= s[12:16].strip()
                    resname = s[17:20].strip()
                    resndx  = int(s[22:26].strip())
                    chain   = s[21]
                    if len(s) > 76 :
                        element = s[77]
                    else :
                        element = 'C'

                    hydrogen = {"H": True}
                    is_hydrogen = hydrogen.get(s[13], False)

                    if resname in protRes :
                        moltype = "Protein"
                    elif resname in DNARes :
                        moltype = "DNA"
                    elif resname in RNARes :
                        moltype = "RNA"
                    else :
                        moltype = "Unknown"

                    if moltype == "Protein" :
                        subgroup = prosubgroup.get(atomname, "Unknown")
                    elif moltype in ["RNA", "DNA"] :
                        subgroup = xnasubgroup.get(atomname, "Unknown")
                    else :
                        subgroup = "Unknown"

                    atominfor[atomndx] = [atomname, moltype, is_hydrogen, resname, resndx, chain, subgroup, element]
                else :
                    pass

        return  atominfor

    def findAtomType(self, information, singleFramePDB):
        atomType = []

        if information in ['Alpha-Carbon', 'CA', 'alpha', 'Ca', 'Alpha']:
            atomType = ['CA']
        elif information in ['main', 'mainchain', 'Mainchain', 'MainChain']:
            atomType = ['CA', 'N', 'C', 'O']
        elif information in ['back', 'backbone', 'Backbone', 'BackBone']:
            atomType = ['CA', 'N']

        elif information in ['noH', 'non-H', 'non-hydrogen', 'Non-H', 'no-h', 'heavy']:
            with open(singleFramePDB) as lines:
                for s in lines:
                    if "ATOM" in s and s.split()[2] not in atomType and s[13] != "H" and s[-1] != "H":
                        atomType.append(s.split()[2])

        elif information in ['all', 'all-atom', 'All-Atom', 'ALL']:
            with open(singleFramePDB) as lines:
                for s in lines:
                    if "ATOM" in s and s.split()[2] not in atomType:
                        atomType.append(s.split()[2])
        elif len(information):
            atomType = [information]
        else:
            print "Error! AtomType not correct. Exit Now! \n"
            sys.exit(1)

        return atomType


    def findAtomNdx(self, pdbfile, resList, chain, atomType, verbose=False):
        '''
        give a pdb file, return the atom ndx needed
        :param pdbfile:
        :param resList:
        :param chain:
        :param atomType:
        :param verbose:
        :return:
        '''
        if verbose :
            print pdbfile, resList, chain, atomType
        atomndx = []
        #append = atomndx.append
        for key in resList.keys() :
            with open(pdbfile) as lines :
                atomndx = [ s.split()[1]
                            for s in lines
                            if len(s.split()) and
                            s[:6].strip() in ["ATOM", "HETATM"] and
                            s.split()[2] in atomType and
                            s[21] in list(chain) and
                            int(s[22:26].strip()) in resList[key] and
                            s.split()[1] not in atomndx
                            ]
                '''
                for s in lines :
                    if "ATOM" in s or "HETATM" in s :
                        if s.split()[2] in atomType and s[21] in list(chain) and int(s[22:26].strip()) in resList[key] :
                            if s.split()[1] not in atomndx :
                                append(s.split()[1])
                            else :
                                pass '''
        return atomndx

    def getPdbCrd(self, singleFramePDB, atomList):
        # input a pdb file return the atom crds in each residue
        # in a dictionary format
        resCrds = []
        resRecord = []

        with open(singleFramePDB) as lines:
            crdPerRes = []
            for s in lines:
                if s[:5].strip() in ['ATOM', 'HETATM'] and "TER" not in s:

                    if s.split()[1] in atomList :
                        if not len(resRecord):
                            resRecord.append(s[21] + s[22:26].strip())

                        if (s[21] + s[22:26].strip()) not in resRecord :
                            resRecord.append(s[21] + s[22:26].strip())
                            resCrds.append(crdPerRes)
                            crdPerRes = []
                        # resIndex = s.split()[4 + len(s[21].strip())] + '_' + s[21]
                        crd_list = []
                        crd_list.append(float(s[30:38].strip()))
                        crd_list.append(float(s[38:46].strip()))
                        crd_list.append(float(s[46:54].strip()))

                        crdPerRes.append(crd_list)

            resCrds.append(crdPerRes)

        ## resCrdDist format : {'123':[[0.0,0.0,0.0],[]]}
        return resCrds

    def getPdbCrdByNdx(self, singleFramePDB, atomNdx):
        atomCrd = []
        with open(singleFramePDB) as lines :
            lines = [s for s in lines if len(s) > 4 and s[:4] in ["ATOM","HETA"] and s.split()[1] in atomNdx]
            atomCrd = map(lambda x: [float(x[30:38].strip()), float(x[38:46].strip()), float(x[46:54].strip())], lines)
        return atomCrd

    def residueContacts(self, resCrd1, resCrd2,
                        distcutoff, countcutoff=1.0,
                        switch=False, verbose=False,
                        rank=0
                        ):
        '''

        :param resCrd1:
        :param resCrd2:
        :param distcutoff: the squared the distance cutoff
        :param countcutoff: number of contacts within a residue
        :param switch: apply a switch function
        :param verbose: verbose
        :return: contact if 1, no contact if zero
        '''
        newlist = []
        dc = 2 * math.sqrt(distcutoff)

        for item1 in resCrd1:
            newlist += [[item1, item2] for item2 in resCrd2]

        distances = [sum(map(lambda x, y: (x - y) ** 2, pair[0], pair[1])) for pair in newlist]
        if verbose :
            print rank, " DISTANCES ", distances

        if switch:
            counts = self.switchFuction(math.sqrt(distances[0]), dc)
            if verbose :
                print rank, " COUNTS: ", counts
            return counts
        else :
            counts = len(filter(lambda x: x <= distcutoff, distances))

            if counts >= countcutoff :
                return 1.0
            else:
                return 0.0

    def subgroupCmap(self, pdbin, cutoff, atomNdx=[], verbose=False, logifle='log.log'):
        if not os.path.exists(pdbin):
            # raise Exception("Boo! \nNot find PDB files for calculation! ")
            print 'Exit Now!'
            sys.exit(1)

        tofile = open(logifle, 'w')

        # elements in atom infor
        # key: atom index
        # value: [atomname, molecule type, is_hydrogen,  resname, resndx, chainid,(mainchian, sidechain,
        #           sugar ring, phosphate group, base ring)]
        # atominfor[atomndx] = [atomname, moltype, is_hydrogen, resname, resndx, chain, subgroup]
        detailatomInfor = self.atomInformation(pdbin)

        atomndx_1 = atomNdx[0]
        atomndx_2 = atomNdx[-1]

        crds1 = self.getPdbCrdByNdx(pdbin, atomndx_1)
        crds2 = self.getPdbCrdByNdx(pdbin, atomndx_2)

        distance_cutoff = cutoff ** 2

        for y in xrange(len(atomndx_2)) :
            atom2 = atomndx_2[y]
            infor2 = detailatomInfor[atom2]
            if infor2[-1] in ['P','S', 'N','O'] :
                for x in xrange(len(atomndx_1)) :
                    atom1 = atomndx_1[x]
                    infor1 = detailatomInfor[atom1]
                    if infor1[-1] in ['P','S', 'N','O']   :
                        crd1 = crds1[x]
                        crd2 = crds2[y]
                        if verbose :
                            print infor1, infor2
                            print crd1, crd2

                        distance =  sum(map(lambda x, y: (x - y) ** 2, crd1, crd2))
                        if verbose :
                            print distance

                        if distance <= distance_cutoff :

                            resid1 = infor1[3] + "_" + str(infor1[4]) + "_" + infor1[6]
                            resid2 = infor2[3] + "_" + str(infor2[4]) + "_" + infor2[6]

                            print resid1, resid2

                            tofile.write("%16s   %-20s   %-4s  %-4s  %8.3f\n"%(resid2, resid1, infor2[0], infor1[0], math.sqrt(distance)))

            if verbose :
                print("complete atom %s "% atom2)

        tofile.close()

        return 1
    def cmap_ca(self, pdbFileList, cutoff, switch=False, atomNdx=[], rank=0, verbose=False, nresidues=0):

        if len(pdbFileList) == 0:
            # raise Exception("Boo! \nNot find PDB files for calculation! ")
            print 'Exit Now!'
            sys.exit(1)

        atomndx_1 = atomNdx[0]
        atomndx_2 = atomNdx[-1]

        distance_cutoff = cutoff ** 2

        if len(atomNdx[0]) * len(atomNdx[-1]) > nresidues :
            countCutoff = 2.0
        else:
            countCutoff = 1.0


        ### start calculate all the pdbfile residue c alpha contact
        contCountMap = [0] * nresidues
        progress = 0
        for pdbfile in pdbFileList:
            progress += 1
            print "Rank %d Progress: The %dth File %s out of total %d files" % \
                  (rank, progress, pdbfile, len(pdbFileList))
            if verbose :
                print rank, atomndx_1, atomndx_2

            resCrdDict1 = self.getPdbCrd(pdbfile, atomndx_1)

            resCrdDict2 = self.getPdbCrd(pdbfile, atomndx_2)

            #mmax = len(resCrdDict1)
            nmax = len(resCrdDict2)

            for m in range(len(resCrdDict1)):
                for n in range(len(resCrdDict2)):
                    if verbose :
                        print rank, " RESIDUES ", m, n, resCrdDict1[m], resCrdDict2[n]

                    contCountMap[n + m * nmax] += self.residueContacts(resCrdDict1[m],
                                                                       resCrdDict2[n],
                                                                       distance_cutoff,
                                                                       countCutoff,
                                                                       switch,
                                                                       verbose,
                                                                       rank
                                                                       )

            print "PDB file " + str(pdbfile) + " Finished!"
            del resCrdDict1, resCrdDict2
        return contCountMap, len(pdbFileList)

    def getResidueName(self, singleFramePDB, resList, chains):
        # input a pdb file return the atom crds in each residue
        # in a dictionary format
        used = []
        for key in resList.keys() :
            with open(singleFramePDB) as lines:
                lines = list(filter(lambda x: ("ATOM" in x or "HETATM" in x) and x[21] in chains, lines))
                resNames = [ x[22:26].strip() + '_' + x[21] for x in lines if int(x[22:26].strip()) in resList[key] ]

                for item in resNames :
                    if item not in used :
                        used.append(item)
        return used

    def writeFiles(self, cmap, nFiles,cmapName, resNames1, resNames2, rank):
        if len(cmap) != len(resNames1) * len(resNames2) :
            print("Fatal Error! Write data to file failed!")
            sys.exit(0)
        else :
            nmax = len(resNames2)
            # generate contact matrix file
            result = open(str(rank) + "_" + cmapName, 'wb')
            result.write("NDX  ")
            for i in resNames2 :
                result.write('%5s ' % str(i))

            # print contCountMap.keys()
            for m in range(len(resNames1)):
                result.write('\n%5s ' % resNames1[m])
                for n in range(len(resNames2)):
                    result.write('%8.1f ' % (cmap[n + m * nmax ]))
            result.close()

            result = open(str(rank) + "_" + cmapName + '.xyz', 'wb')
            result.write("# Receptor Ligand Contact_probability \n")
            for i in range(len(resNames1)):
                for j in range(len(resNames2)) :
                    result.write('%5s  %5s  %8.4f \n' % (resNames1[i], resNames2[j], cmap[j+i*nmax]/nFiles ))
            result.close()

if __name__ == "__main__" :
    ## change to working directory
    pwd = os.getcwd()
    os.chdir(pwd)

    startTime = datetime.now()

    d = '''
    ########################################################################
    #  Script for generating contact probability map                       #
    #  Author:  ZHENG Liangzhen                                            #
    #  Email:   LZHENG002@e.ntu.edu.sg                                     #
    #  Version: V2.0                                                       #
    #  Date:    15 Sept 2015                                               #
    ########################################################################

    Generating contact probability Map (Cmap)

    Input a multi-frame pdb (MFPDB file) file to construct a contact probability map.
    This MFPDB have multiple models in a single file, and all the structures should
    stay whole, broken structures will cause inaccurate results.
    All the frames in MFPDB do not consider PBC conditions, you should keep structures
    as a whole.

    If some arguements not given, default values would be used.

    Usage:
    1. Show help information
    python ContactMap.py -h

    2. Construct a Ca-Ca Cmap for a protein chain
    python ContactMap.py -inp MF_pro.pdb -out Cmap.dat -rc A 1 250
    -lc A 1 250 -cutoff 3.5 -switch T -atomtype CA

    3. Generate a full-atom Cmap for a poly-peptide chain
    python ContactMap.py -inp MF_pro.pdb -out Cmap.dat -rc A 1 250
    -lc A 1 250 -cutoff 3.5 -atomtype all all

    4. Construct a Cmap between a small ligand and a protein
    python ContactMap.py -inp MF_pro.pdb -out Cmap.dat -rc A 1 250
    -lc A 251 251 -cutoff 3.5 -atomtype all all

    5. Construct a Cmap between a small ligand and a protein, Ca-allatom
    python ContactMap.py -inp MF_pro.pdb -out Cmap.dat -rc A 1 250
    -lc A 251 251 -cutoff 3.5 -atomtype CA all

    6. Construct a cmap between a protein chain with MPI
    mpirun -np 4 python ContactMap.py -inp MF_pro.pdb -out Cmap.dat -rc A 1 250
    -lc A 251 251 -cutoff 3.5 -atomtype CA all -np 4

    '''
    parser = argparse.ArgumentParser(description=d, formatter_class=RawTextHelpFormatter)
    parser.add_argument('-inp', type=str, help="The input huge PDB file with multiple frames")
    parser.add_argument('-out',type=str, default='ContactMap.dat',
                        help="The output file name. Default name is ContactMap.dat \n")
    parser.add_argument('-rc',type=str,nargs='+', default=['A','1','250'],
                        help="The receptor chains and residue index for Cmap construction.\n"
                             "You must enter a chain name, start residue index, and end chain index.\n"
                             "Default is: A 1 250 \n")
    parser.add_argument('-lc', type=str, nargs='+', default=['A','1','250'],
                        help="The ligand chains and residue index for Cmap construction.\n"
                             "You must enter a chain name, start residue index, and end chain index.\n"
                             "Default is: B 1 250 \n" )
    parser.add_argument('-cutoff',type=float,default=0.35,
                        help="Distance Cutoff for determining contacts. \n"
                             "Default is 3.5 (angstrom). \n")
    parser.add_argument('-atomtype',type=str,nargs='+', default=[],
                        help="Atom types for Receptor and Ligand in Contact Map Calculation. \n"
                             "Only selected atoms will be considered.\n"
                             "Options: CA, Backbone, MainChain, All, non-H(All-H). \n"
                             "CA, alpha-carbon atoms. Backbone, backbone atoms in peptides. \n"
                             "MainChain, including CA and N atoms. All, means all atoms.\n"
                             "non-H, non-hydrogen atoms, all the heavy atoms. \n"
                             "Two choices should be provided for receptor and ligand respectively. \n"
                             "If only one atomtype given, the 2nd will be the same as 1st.\n"
                             "Default is: [] \n")
    parser.add_argument('-atomname1', type=str, nargs='+', default=[],
                        help="Atom names for Recetpor in Contact Map. \n"
                             "Default is []. ")
    parser.add_argument('-atomname2', type=str, nargs='+', default=[],
                        help="Atom names for Ligand in Contact Map. \n"
                             "Default is []. ")
    parser.add_argument('-switch', type=str, default='True',
                        help="Apply a switch function for determing Ca-Ca contacts for a smooth transition. \n"
                             "Only work with atomtype as CA. Options: True(T, t. TRUE), False(F, f, FALSE) \n"
                             "Default is False. \n")
    parser.add_argument('-np', default=0, type=int,
                        help='Number of Processers for MPI. Interger value expected. \n'
                             'If 4 is given, means using 4 cores or processers.\n'
                             'If 0 is given, means not using MPI, using only 1 Core.\n'
                             'Default is 0. ')
    parser.add_argument('-test', default=0, type=int,
                        help="Do a test with only a number of frames. For example, 4 frames. \n"
                             "Default value is 0. ")

    parser.add_argument('-verbose', default=0 , type=int,
                        help="Verbose. Default is False.")
    parser.add_argument('-details', default=None, type=str,
                        help="Provide detail contact information and write out to a file. \n"
                             "Default is None."
                        )

    args = parser.parse_args()

    if args.np > 0 :

        cmap = ContactMap(args.inp)

        reference = cmap.extractReference()
        # decide to print help message
        if len(sys.argv) < 2:
            # no enough arguements, exit now
            parser.print_help()
            print "You chose non of the arguement!\nDo nothing and exit now!\n"
            sys.exit(1)

        comm = MPI.COMM_WORLD
        size = comm.Get_size()
        rank = comm.rank

        #pdbFileList = sorted(glob.glob("./S_*.pdb"))[:12]

        atomType = []
        atomName1 = args.atomname1
        atomName2 = args.atomname2
        if len(args.atomtype) == 1:
            atomType.append(cmap.findAtomType(args.atomtype[0], args.inp))
            atomType.append(cmap.findAtomType(args.atomtype[0], args.inp))
        elif len(args.atomtype) == 2:
            atomType.append(cmap.findAtomType(args.atomtype[0], args.inp))
            atomType.append(cmap.findAtomType(args.atomtype[1], args.inp))
        else:

            atomType = [ args.atomname1, args.atomname2 ]

        if atomType == [['CA'],['CA']] :
            switch = args.switch
        else :
            switch = False

        ## receptor information about residues
        rcResNdx = defaultdict(list)
        round = len(args.rc) / 3
        rcChains = []
        for i in range(round):
            rcResNdx[args.rc[i * 3]] = range(int(args.rc[i * 3 +1]),int(args.rc[i *3+2]) + 1)
            rcChains.append(args.rc[(i + 1) * 3 - 3])

        #print rcResNdx
        lcResNdx = defaultdict(list)
        round = len(args.lc) / 3
        lcChains = []
        for i in range(round):
            lcChains.append(args.lc[i*3])
            lcResNdx[args.lc[i * 3]] = range(int(args.lc[i * 3 + 1]), int(args.lc[i * 3 + 2]) + 1)
        #print lcResNdx
        ## start to construct map
        receptorAtomNdx = cmap.findAtomNdx(reference, rcResNdx, rcChains, atomType[0], args.verbose)
        ligandAtomNdx   = cmap.findAtomNdx(reference, lcResNdx, lcChains, atomType[-1], args.verbose)

        if args.verbose :
            print "ATOM NDX"
            print receptorAtomNdx, ligandAtomNdx

        if args.details :
            cmap.subgroupCmap(reference, args.cutoff, [receptorAtomNdx, ligandAtomNdx], args.verbose, args.details)

            #sys.exit(1)
        else :

            if rank == 0:
                if args.test:
                    pdbFileList = sorted(cmap.splitPdbFile())[: args.test]
                else:
                    pdbFileList = sorted(cmap.splitPdbFile())
            else:
                pdbFileList = None

            pdbFileList = comm.bcast(pdbFileList, root=0)
            totalNumOfFiles = len(pdbFileList)

            if rank == 0 :

                load4each = int(math.ceil(float(totalNumOfFiles) / float(args.np)))
                filesList = []

                for i in range(args.np - 1) :
                    filesList.append(pdbFileList[i * load4each : load4each * (i+1)])
                filesList.append(pdbFileList[(args.np-1)*load4each:])

                if args.verbose:
                    print "Full File List " * 10, pdbFileList, filesList

            else :
                filesList = []

            ## scatter data to sub-processers
            filesList = comm.scatter(filesList, root=0)

            recNames = cmap.getResidueName(filesList[0], rcResNdx, rcChains)
            ligNames = cmap.getResidueName(filesList[0], lcResNdx, lcChains)

            Cmap, nFiles = cmap.cmap_ca(filesList, args.cutoff,
                                        switch,
                                        [receptorAtomNdx, ligandAtomNdx],
                                        rank, args.verbose, len(recNames)*len(ligNames)
                                        )

            cmap.writeFiles(Cmap, nFiles,args.out, recNames, ligNames, rank)

            overallValuesList = comm.gather(Cmap, root=0)

            ## once calculation done, wrap up to write data out
            if rank == 0 :
                # "Wrap Up and write data to files "
                final = np.zeros(len(Cmap))
                for rank_values in overallValuesList :
                    final += np.asarray(rank_values)

                final = final / float(size)

                cmap.writeFiles(final, totalNumOfFiles, args.out, recNames, ligNames, rank='all')

        if rank == 0:
            print "Total Time Usage: "
            print datetime.now() - startTime

        MPI.Finalize()
        sys.exit(1)