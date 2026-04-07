import numpy as np
import pandas as pd
from hspf import build_warehouse

def transform_timeseries(opcode, A=None, B=None, c=None):
    """
    Transform a timeseries based on the given opcode.
    
    OPCODE                  Action
        1             C= Abs value (A)
        2             C= Square root (A)
        3             C= Truncation (A)
                         e.g., If A=4.2,  C=4.0
                                 A=-3.5, C=-3.0
        4             C= Ceiling (A). The “ceiling” is
                         the integer >= given value.
                         e.g., If A=3.5,  C=4.0
                                 A=-2.0, C=-2.0
        5             C= Floor (A). The “floor” is the
                         integer <= given value.
                         e.g., If A=3.0,  C=3.0
                                 A=-2.7, C=-3.0
        6             C= loge (A)
        7             C= log10 (A)
        8             C= K(1)+K(2)*A+K(3)*A**2 (up to 7 terms)
                         The user supplies the number of
                         terms and the values of the
                         coefficients (K).
        9             C= K**A
       10             C= A**K
       11             C= A+K
       12             C= Sin (A)
       13             C= Cos (A)
       14             C= Tan (A)
       15             C= Sum (A)
       16             C= A+B
       17             C= A-B
       18             C= A*B
       19             C= A/B
       20             C= MAX (A,B)
       21             C= MIN (A,B)
       22             C= A**B
       23             C= cumulative departure of A below B
       24             C= K
       25             C= Max (A,K)
       26             C= Min (A,K)

    Args:
        opcode: Integer code indicating the operation (1-26)
        A: Input timeseries (array-like)
        B: Second input timeseries (array-like), optional
        c: List of coefficients, optional
    
    Returns:
        Transformed timeseries
    """
    A = np.asarray(A)
    
    if opcode == 1:
        return np.abs(A)
    elif opcode == 2:
        return np.sqrt(A)
    elif opcode == 3:
        return np.trunc(A)
    elif opcode == 4:
        return np.ceil(A)
    elif opcode == 5:
        return np.floor(A)
    elif opcode == 6:
        return np.log(A)
    elif opcode == 7:
        return np.log10(A)
    elif opcode == 8:
        result = np.zeros_like(A, dtype=float)
        for i, coeff in enumerate(c):
            result += coeff * (A ** i)
        return result
    elif opcode == 9:
        return (c[0] ** A)
    elif opcode == 10:
        return (A ** c[0])
    elif opcode == 11:
        return A + c[0]
    elif opcode == 12:
        return np.sin(A)
    elif opcode == 13:
        return np.cos(A)
    elif opcode == 14:
        return np.tan(A)
    elif opcode == 15:
        return np.cumsum(A)
    elif opcode == 16:
        return A + np.asarray(B)
    elif opcode == 17:
        return A - np.asarray(B)
    elif opcode == 18:
        return A * np.asarray(B)
    elif opcode == 19:
        return A / np.asarray(B)
    elif opcode == 20:
        return np.maximum(A, np.asarray(B))
    elif opcode == 21:
        return np.minimum(A, np.asarray(B))
    elif opcode == 22:
        return A ** np.asarray(B)
    elif opcode == 23:
        return np.cumsum(np.minimum(A - np.asarray(B), 0))
    elif opcode == 24:
        return np.full_like(A, c[0], dtype=float)
    elif opcode == 25:
        return np.maximum(A, c[0])
    elif opcode == 26:
        return np.minimum(A, c[0])
    else:
        raise ValueError(f"Unknown opcode: {opcode}")


def instructions(uci):
    # GENER timeseries inputs SCHEMATIC and/or Network
    df_schematic = uci.table('SCHEMATIC').query('TVOL == "GENER"')

    df_network = uci.table('NETWORK').rename(columns = {'TOPFST':'TVOLNO'})
    df = df_network.loc[(df_network['SVOL'] == 'GENER') & (df_network['TRAN'] == 'SAME')]
    # Switch the Source and Target information when TRAN is SAME and the SVOL is a GENER as it appears in some cases 
    # You can define the gener input timeseries backwards
    df2 = df.copy()
    df.loc[:,['SVOL','SVOLNO','SGRPN','SMEMN','SMEMSB1','SMEMSB2']] = df.loc[:,['TVOL','TVOLNO','TGRPN','TMEMN','TMEMSB1','TMEMSB2']]
    df.loc[:,['TVOL','TVOLNO','TGRPN','TMEMN','TMEMSB1','TMEMSB2']] = df2.loc[:,['SVOL','SVOLNO','SGRPN','SMEMN','SMEMSB1','SMEMSB2']]
    df_network = df_network.loc[df_network['TVOL'] == 'GENER']
    df_network = pd.concat([df_network,df])

    df_masslinks = build_warehouse.build_masslink_table(model_name,uci)
    df = pd.merge(df_schematic, df_masslinks, left_on=['MLNO','SVOL','TVOL'], right_on = ['MLNO','SVOL','TVOL'])
    #Repalce the values in TMEMSB1_y and TMEMSB2_y with the values in TMEMSB1_x and TMEMSB2_x when TMEMSB1_x is not '' TMEMSB2_x is not ''
    df['TMEMSB1'] = df.apply(lambda row: row['TMEMSB1_x'] if row['TMEMSB1_x'] != '' else row['TMEMSB1_y'], axis=1)
    df['TMEMSB2'] = df.apply(lambda row: row['TMEMSB2_x'] if row['TMEMSB2_x'] != '' else row['TMEMSB2_y'], axis=1)
    df = pd.concat([df,df_network])

    df_gener = build_warehouse.build_gener_table(model_name,uci).reset_index()
    df = pd.merge(df_gener,df, left_on = 'OPNID',right_on = 'TVOLNO')


    df = df[['SVOL','SVOLNO','AFACTR','MFACTOR','TRAN','TVOL','TVOLNO','MLNO','TMEMN','TMEMSB1','TMEMSB2','SGRPN','SMEMN','SMEMSB1','SMEMSB2','MFACTOR','TGRPN','OPCODE','K']]
    return df

# def get_coefficents(uci,opnid,opcode):
#     if opcode == 8:
#         c = list(uci.table('GENER','COEFFS').loc[opnid].values)
#     elif opcode in [9, 10, 11, 24, 25, 26]:
#         c = list(uci.table('GENER','PARM').loc[opnid].values)
#     else:
#         c = None
#     return c

# start_date = uci.table('GLOBAL')['start_date']
# end_date = uci.table('GLOBAL')['end_date']
# datetime = pd.date_range(start=start_date, end=end_date,freq='h')
# opnid = 1
# opcode = 24
# k = 1


# def get_timeseries(uci, opnid):
#     opcode = uci.table('GENER','OPCODE').loc[opnid,'OPCODE']
#     c = get_coefficents(uci, opnid, opcode)
#     A = None
#     B = None

#     if opcode == 24:
#         start_date = uci.table('GLOBAL')['start_date']
#         end_date = uci.table('GLOBAL')['end_date']
#         A = pd.date_range(start=start_date, end=end_date,freq='h')
    
#     else:
#         if 'NETWORK' in uci.block_names():
#             network = uci.table('NETWORK').query('TVOL == "GENER" & TOPFST == @opnid')
#         if 'SCHEMATIC' in uci.block_names():
#             schematic = uci.table('SCHEMATIC').query('TVOL == "GENER" & TVOLNO == @opnid')
#             mlno = schematic['MLNO'].values[0]
#             masslink = uci.table('MASS-LINK',f'MASS-LINK{mlno}')
#             df = pd.merge(schematic,masslink, left_on='MLNO', right_on='MLNO')

#         df = network.query('TVOL == "GENER" & TOPFST == @opnid')
#         for index, row in df.iterrows():
#             if row['SVOL'] == 'GENER':
#                 get_timeseries(uci, row['SVOLNO'])
#             else:

# # GENER timeseries inputs SCHEMATIC and/or Network
# df_schematic = uci.table('SCHEMATIC').query('TVOL == "GENER"')
# df_network = uci.table('NETWORK').query('TVOL == "GENER"').rename(columns = {'TOPFST':'TVOLNO'})
# df_masslinks = build_warehouse.build_masslink_table(model_name,uci)
# df = pd.merge(df_schematic, df_masslinks, left_on=['MLNO','SVOL','TVOL'], right_on = ['MLNO','SVOL','TVOL'])
# #Repalce the values in TMEMSB1_y and TMEMSB2_y with the values in TMEMSB1_x and TMEMSB2_x when TMEMSB1_x is not '' TMEMSB2_x is not ''
# df['TMEMSB1'] = df.apply(lambda row: row['TMEMSB1_x'] if row['TMEMSB1_x'] != '' else row['TMEMSB1_y'], axis=1)
# df['TMEMSB2'] = df.apply(lambda row: row['TMEMSB2_x'] if row['TMEMSB2_x'] != '' else row['TMEMSB2_y'], axis=1)
# df = pd.concat([df,df_network])

# df_gener = build_warehouse.build_gener_table(model_name,uci).reset_index()
# df = pd.merge(df_gener,df, left_on = 'OPNID',right_on = 'TVOLNO')


# df = df[['SVOL','SVOLNO','AFACTR','MFACTOR','TRAN','TVOL','TVOLNO','MLNO','TMEMN','TMEMSB1','TMEMSB2','SGRPN','SMEMN','SMEMSB1','SMEMSB2','MFACTOR','TGRPN','OPCODE','K']]


# # INPUT timeseries are defined within the NETWORK table or the SCHEMATIC/MASS-LINK tables


# transform_timeseries(opcode, A=datetime, c=[0])




# uci.table('GENER','OPCODE')

