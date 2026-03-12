# -*- coding: utf-8 -*-
"""
Created on Wed Nov 10 15:48:19 2021

@author: mfratki
"""
import pandas as pd
import numpy as np
#import subprocess
from pathlib import Path 



def decompose_perlands(metzones,landcovers):
    perlands = {}
    for metzone in metzones:
        metzone = int(metzone)
        for landcover in landcovers:
            landcover = int(landcover)
            perlands[metzone+landcover] = (metzone,landcover)
    return perlands



def get_months(month):
    months = {1:'JAN', 2:'FEB', 3:'MAR', 4:'APR', 5:'MAY', 6:'JUN', 7:'JUL',
           8:'AUG', 9:'SEP', 10:'OCT', 11:'NOV', 12:'DEC'}
    return months[month]

def get_adjacent_month(month,side = 1):
    months = {1:[12,2], 2:[1,3], 3:[2,4], 4:[3,5], 5:[4,6], 6:[5,7], 7:[6,8],
           8:[7,9], 9:[8,10], 10:[9,11], 11:[10,12], 12:[11,1]}
    return months[month][side]

def get_tcons(nutrient_name,operation,units = 'mg/l'):
    ''' Convience function for getting the consntituent time series names associated with the nutrients we are
    calibrating for. Note tehat Qual Prop 4 (BOD)
    '''
    
    if operation == 'RCHRES':
        MAP = {'mg/l':{'TSS' :['SSEDTOT'], # TSS
                  'TKN' :['TAMCONCDIS','NTOTORGCONC'], # TKN
                  'N' :['NO2CONCDIS','NO3CONCDIS'], # N
                  'TN': ['NTOTCONCDIS'], # Total Nitrogen
                  'OP' :['PO4CONCDIS'], # Ortho
                  'TP' :['PTOTCONC']},# BOD is the difference of ptot and ortho
         'lb': {'TSS' :['ROSEDTOT'], # TSS
                  'TKN' :['TAMOUTTOT','NTOTORGOUT'], # TKN
                  'N' :['NO3OUTTOT','NO2OUTTOT'], # N
                  'TN': ['NTOTOUT'], # Total Nitrogen
                  'OP' :['PO4OUTDIS'], # Ortho
                  'TP' :['PTOTOUT'],
                  'BOD' :['BODOUTTOT'],},
        'cfs': {'Q': ['ROVOL']},
        'acrft' : {'Q': ['ROVOL']},
        'degf' : {'WT': ['TW']}}
        
        t_cons = MAP[units]
    elif operation == 'PERLND':
        t_cons = {'TSS' :['SOSED'],
                  'TKN' :['POQUALNH3+NH4'],
                  'N' :['POQUALNO3'],
                  'OP' :['POQUALORTHO P'],
                  'BOD' :['POQUALBOD'],
                  'Q' : ['PERO']} # BOD is the difference of ptot and ortho
    elif operation == 'IMPLND':
        t_cons = {'TSS' :['SLDS'],
                  'TKN' :['SOQUALNH3+NH4'],
                  'N' :['SOQUALNO3'],
                  'OP' :['SOQUALORTHO P'],
                  'BOD' :['SOQUALBOD'],
                  'Q' : ['SURO']} # BOD is the difference of ptot and ortho
    else:
        raise ValueError(f'Operation {operation} not recognized for nutrient time constituent lookup.')
    return t_cons[nutrient_name]


def nutrient_name(nutrient_id: int):
    key = {0:'TSS',
           1:'TKN',
           2:'N',
           3:'OP',
           4:'TP',# REally this is BOD but you subtract orthophosphate to get BOD
           5:'ChlA',
           6:'DO',
           7: 'Q'} 
    return key[nutrient_id]

def nutrient_id(nutrient_name: str):
    key = {'TSS' :0,
           'TKN' :1,
           'N'   :2,
           'OP'  :3,
           'TP'  :4, # REally this is BOD but you subtract orthophosphate to get BOD
           'ChlA':5,
           'DO'  :6,
           'Q'   :7} 
    return key[nutrient_name]
