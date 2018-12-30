#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Auxiliary functions library for data fusion from reports extractor, dicoms and dicom anonymization, etc
# Copyright (C) 2017-2019 Stephen Karl Larroque
# Licensed under MIT License.
# v2.5.2
#

from __future__ import absolute_import

import ast
import csv
import os
import re
from .dateutil import parser as dateutil_parser
from .distance import distance

import pandas as pd

try:
    from scandir import walk # use the faster scandir module if available (Python >= 3.5), see https://github.com/benhoyt/scandir
except ImportError as exc:
    from os import walk # else, default to os.walk()

try:
    # to convert unicode accentuated strings to ascii
    from .unidecode import unidecode
    _unidecode = unidecode
except ImportError as exc:
    # native alternative but may remove quotes and some characters (and be slower?)
    import unicodedata
    def _unidecode(s):
        return unicodedata.normalize('NFKD', s).encode('ascii', 'ignore')
    print("Notice: for reliable ascii conversion, you should pip install unidecode. Falling back to native unicodedata lib.")

try:
    from .tqdm import tqdm
    _tqdm = tqdm
except ImportError as exc:
    def _tqdm(*args, **kwargs):
        if args:
            return args[0]
        return kwargs.get('iterable', None)

try:
    from StringIO import StringIO as _StringIO
except ImportError as exc:
    from io import StringIO as _StringIO

def save_dict_as_csv(d, output_file, fields_order=None, csv_order_by=None, verbose=False):
    """Save a dict/list of dictionaries in a csv, with each key being a column"""
    # Define CSV fields order
    # If we were provided a fields_order list, we will show them first, else we create an empty fields_order
    if fields_order is None:
        fields_order = []
    # Get dict/list values
    if isinstance(d, dict):
        dvals = d.values()
    else:
        dvals = d
    # Then automatically add any other field (which order we don't care, they will be appended in alphabetical order)
    fields_order_check = set(fields_order)
    for missing_field in sorted(dvals[0]):
        if missing_field not in fields_order_check:
            fields_order.append(missing_field)
    if verbose:
        print('CSV fields order: '+str(fields_order))

    # Write the csv
    with open(output_file, 'wb') as f:  # Just use 'w' mode in 3.x
        w = csv.DictWriter(f, fields_order, delimiter=';')
        w.writeheader()
        # Reorder by name (or by any other column)
        if csv_order_by is not None:
            d_generator = sorted(dvals, key=lambda x: x[csv_order_by])
        else:
            d_generator = dvals
        # Walk the ordered list of dicts and write each as a row in the csv!
        for d_fields in d_generator:
            w.writerow(d_fields)
    return True


def save_df_as_csv(d, output_file, fields_order=None, csv_order_by=None, keep_index=False, encoding='utf-8', verbose=False, **kwargs):
    """Save a dataframe in a csv"""
    # Define CSV fields order
    # If we were provided a fields_order list, we will show them first, else we create an empty fields_order
    if fields_order is None:
        fields_order = []
    # Then automatically add any other field (which order we don't care, they will be appended in alphabetical order)
    fields_order_check = set(fields_order)
    for missing_field in sorted(d.columns):
        if missing_field not in fields_order_check:
            fields_order.append(missing_field)
    if verbose:
        print('CSV fields order: '+str(fields_order))

    # Write the csv
    if csv_order_by is not None:
        d = d.sort_values(csv_order_by)
    else:
        d = d.sort_index()
    d.to_csv(output_file, sep=';', index=keep_index, columns=fields_order, encoding=encoding, **kwargs)
    return True


def distance_jaccard_words(seq1, seq2, partial=False, norm=False, dist=0, minlength=0):
    """Jaccard distance on two lists of words. Any permutation is tested, so the resulting distance is insensitive to words order.
    @param dist float Set to any value above 0 to get fuzzy matching (ie, a word matches if character distance < dist)
    @param partial boolean Set to True to match words if one of the two starts with the other (eg: 'allan' and 'al' will match) - combine with minlength to ensure a minimum length to match
    @param norm [True/False/None] True to get normalized result (number of equal words divided by total words count from both), False to get the number of different words, None to get the number of equal words.
    @param minlength int Minimum number of caracters to allow comparison and matching between words (else a word smaller than this will be a 'dead weight' if norm=True in the sense that it will still be accounted in the total but cannot be matched)"""
    # The goal was to have a distance on words that 1- is insensible to permutation ; 2- returns 0.2 or less if only one or two words are different, except if one of the lists has only one entry! ; 3- insensible to shortened name ; 4- allow for similar but not totally exact words.
    seq1_c = filter(None, list(seq1))
    seq2_c = filter(None, list(seq2))
    count_total = len(seq1_c) + len(seq2_c)
    count_eq = 0
    for s1 in seq1_c:
        flag_eq = False
        for skey, s2 in enumerate(seq2_c):
            if minlength and (len(s1) < minlength or len(s2) < minlength):
                continue
            if s1 == s2 or \
            (partial and (s1.startswith(s2) or s2.startswith(s1))) or \
            (dist and distance.nlevenshtein(s1, s2, method=1) <= dist):
                count_eq += 1
                del seq2_c[skey]
                break
    # Prepare the result to return
    if norm is None:
        # Just return the count of equal words
        return count_eq
    else:
        count_eq *= 2  # multiply by two because everytime we compared two items
        if norm:
            # Normalize distance
            return 1.0 - (float(count_eq) / count_total)
        else:
            # Return number of different words
            return count_total - count_eq

def distance_jaccard_words_split(s1, s2, *args, **kwargs):
    """Split sentences in words and call distance jaccard for words"""
    wordsplit_pattern = kwargs.get('wordsplit_pattern', None)
    if 'wordsplit_pattern' in kwargs:
        del kwargs['wordsplit_pattern']
    if not wordsplit_pattern:
        wordsplit_pattern = r'\s+|_+|,+|\.+|/+';  # do not split on -+| because - indicates a single word/name

    return distance_jaccard_words(re.split(wordsplit_pattern, s1), re.split(wordsplit_pattern, s2), *args, **kwargs)

def fullpath(relpath):
    '''Relative path to absolute'''
    if (type(relpath) is object or hasattr(relpath, 'read')): # relpath is either an object or file-like, try to get its name
        relpath = relpath.name
    return os.path.abspath(os.path.expanduser(relpath))

def recwalk(inputpath, sorting=True, folders=False, topdown=True, filetype=None):
    '''Recursively walk through a folder. This provides a mean to flatten out the files restitution (necessary to show a progress bar). This is a generator.'''
    if filetype and isinstance(filetype, list):
        filetype = tuple(filetype)  # str.endswith() only accepts a tuple, not a list
    # If it's only a single file, return this single file
    if os.path.isfile(inputpath):
        abs_path = fullpath(inputpath)
        yield os.path.dirname(abs_path), os.path.basename(abs_path)
    # Else if it's a folder, walk recursively and return every files
    else:
        for dirpath, dirs, files in walk(inputpath, topdown=topdown):	
            if sorting:
                files.sort()
                dirs.sort()  # sort directories in-place for ordered recursive walking
            # return each file
            for filename in files:
                if not filetype or filename.endswith(filetype):
                    yield (dirpath, filename)  # return directory (full path) and filename
            # return each directory
            if folders:
                for folder in dirs:
                    yield (dirpath, folder)

def sort_list_a_given_list_b(list_a, list_b):
    return sorted(list_a, key=lambda x: list_b.index(x))

def replace_buggy_accents(s, encoding=None):
    """Fix weird encodings that even ftfy cannot fix"""
    # todo enhance speed? or is it the new regex on name?
    dic_replace = {
        '\xc4\x82\xc2\xa8': 'e',
        'ĂŠ': 'e',
        'Ăť': 'u',
        'â': 'a',
        'Ă´': 'o',
        'Â°': '°',
        'â': "'",
        'ĂŞ': 'e',
        'ÂŤ': '«',
        'Âť': '»',
        'Ă': 'a',
        'AŠ': 'e',
        'AŞ': 'e',
        'A¨': 'e',
        'A¨': 'e',
        'Ă': 'E',
        'â˘': '*',
        'č': 'e',
        '’': '\'',
    }
    for pat, rep in dic_replace.items():
        if encoding:
            pat = pat.decode(encoding)
            rep = rep.decode(encoding)
        s = s.replace(pat, rep)
    return s

def cleanup_name(s, encoding='latin1', normalize=True, clean_nonletters=True):
    s = _unidecode(s.decode(encoding).replace('^', ' '))
    if normalize:
        s = s.lower().strip()
    if clean_nonletters:
        s = re.sub('\-+', '-', re.sub('\s+', ' ', re.sub('[^a-zA-Z0-9\-]', ' ', s))).strip().replace('\r', '').replace('\n', '').replace('\t', '').replace(',', ' ').replace('  ', ' ').strip()  # clean up spaces, punctuation and double dashes in name
    return s

# Compute best diagnosis for each patient
def compute_best_diag(serie, diag_order=None, persubject=True):
    """Convert a serie to a categorical type and extract the best diagnosis for each subject (patient name must be set as index level 0)
    Note: case insensitive and strip spaces automatically"""
    if diag_order is None:
        diag_order = ['coma', 'vs/uws', 'mcs', 'mcs-', 'mcs+', 'emcs', 'lis']  # from least to best
    # Convert to lowercase
    diag_order = [x.lower().strip() for x in diag_order]
    # Check if our list of diagnosis covers all possible in the database, else raise an error
    possible_diags = serie.str.lower().str.strip().dropna().unique()
    try:
        assert not set([x.lower().strip() for x in possible_diags]) - set([x.lower().strip() for x in diag_order])
    except Exception as exc:
        raise ValueError('The provided list of diagnosis does not cover all possible diagnosis in database. Please fix the list. Here are the possible diagnosis from database: %s' % str(possible_diags))

    #for subjname, d in cf_crsr_all.groupby(level=0):
    #    print(d['CRSr::Computed Outcome'])

    if persubject:
        # Return one result per patient
        return serie.str.lower().str.strip().astype(pd.api.types.CategoricalDtype(categories=diag_order, ordered=True)).max(level=0)
    else:
        # Respect the original keys and return one result for each key (can be multilevel, eg subject + date)
        return serie.str.lower().str.strip().astype(pd.api.types.CategoricalDtype(categories=diag_order, ordered=True)).groupby(level=range(serie.index.nlevels)).max()

def merge_two_df(df1, df2, col='Name', dist_threshold=0.2, dist_words_threshold=0.2, mode=0, skip_sanity=False, keep_nulls=True, returnmerged=False, keep_lastname_only=False, prependcols=None, fillna=False, verbose=False, **kwargs):
    """Compute the remapping between two dataframes based on one column, with similarity matching (normalized character-wise AND words-wise levenshtein distance)
    mode=0 is or test, 1 is and test.
    `keep_nulls=True` if you want to keep all records from both databases, False if you want only the ones that match both databases, 1 or 2 if you want specifically the ones that are in 1 or in 2
    `col` can either be a string for a merge based on a single column (usually name), or an OrderedDict of multiple columns names and types, following this formatting: [OrderedDict([('column1_name', 'column1_type'), ('column2_name', 'column2_type')]), OrderedDict([...])] so that you have one ordered dict for each input dataframe, and with the same number of columns (even if the names are different) and in the same order (eg, name is first column, date of acquisition as second column, etc)
    If `fillna=True`, subjects with multiple rows/sessions will be squashed and rows with missing infos will be completed from rows where the info is available (in case there are multiple information, they will all be present as a list). This is only useful when merging (and hence argument `col`) is multi-columns. The key columns are never filled, even if `fillna=True`.
    """
    ### Preparing the input dataframes
    # If the key column is in fact a list of columns (so we will merge on multiple columns), we first extract and rename the id columns for ease
    if isinstance(col, list):
        # Make a backup of the columns
        keycol = list(col)
        # Extract id columns (type = 'id')
        keyid1 = [(x, y) for x,y in keycol[0].items() if y == 'id'][0][0]
        keyid2 = [(x, y) for x,y in keycol[1].items() if y == 'id'][0][0]
        # Rename second dataframe to have the same id column name as the first (easier merge)
        df2.rename(columns={keyid2: keyid1}, inplace=True)
        # Use the id column of first dataframe as the main joining column
        col = keyid1
        # Rename in our keycol
        if keyid2 != keyid1:
            keycol[1][keyid1] = keycol[1][keyid2]
            del keycol[1][keyid2]
    else:
        keycol = None
    # Reset keys
    #df1.reset_index(drop=True, inplace=True)
    #df2.reset_index(drop=True, inplace=True)
    # Find and rename any column "Name" or "NAME" to lowercase "name"
    df1 = df_cols_lower(df1, col=col)
    df2 = df_cols_lower(df2, col=col)
    # drop all rows where all cells are empty or where name is empty (necessary else this will produce an error, we expect the name to exist)
    df1 = df1.dropna(how='all').dropna(how='any', subset=[col])
    df2 = df2.dropna(how='all').dropna(how='any', subset=[col])
    # Rename all columns if user wants, except the key columns (else the merge would not work) - this is an alternative to automatic column renaming in case of conflict
    if prependcols is not None and len(prependcols) == 2:
        if keycol:
            # Multi-columns merging: we drop all the key columns
            df1.rename(columns={c: prependcols[0]+c for c in df1.columns.drop(keycol[0].keys())}, inplace=True)
            df2.rename(columns={c: prependcols[1]+c for c in df2.columns.drop(keycol[1].keys())}, inplace=True)
        else:
            # Single column merging: we drop the one key column
            df1.rename(columns={c: prependcols[0]+c for c in df1.columns.drop(col)}, inplace=True)
            df2.rename(columns={c: prependcols[1]+c for c in df2.columns.drop(col)}, inplace=True)
    # Check if columns are colluding (ie, apart from keys, some columns have the same name) then rename them by prepending "a." and "b."
    cols_conflict = set(df1.columns).intersection(set(df2.columns)).difference(set([col]))
    if len(cols_conflict) > 0:
        if verbose:
            print('Warning: columns naming conflicts detected: will automatically rename the following columns to avoid issues: %s' % str(cols_conflict))
        df1.rename(columns={c: 'a.'+c for c in cols_conflict}, inplace=True)
        df2.rename(columns={c: 'b.'+c for c in cols_conflict}, inplace=True)
    # Make a backup of the original name
    df1[col+'_orig'] = df1[col]
    df2[col+'_orig2'] = df2[col]
    # if doing multiple consecutive merges, a name can in fact be a list of concatenated names, then extract the first name in the list
    # TODO: enhance this to account for all names when comparing
    df1[col] = df1[col].apply(lambda x: df_literal_eval(x)[0] if isinstance(df_literal_eval(x), list) else x)
    df2[col] = df2[col].apply(lambda x: df_literal_eval(x)[0] if isinstance(df_literal_eval(x), list) else x)
    # keep only the lastname (supposed to be first), this can ease comparison
    if keep_lastname_only:
        df1[col] = df1[col].apply(lambda x: x.split()[0])
        df2[col] = df2[col].apply(lambda x: x.split()[0])
    ### Prepare merging variables
    dmerge = []  # result of the merge mapping
    list_names1 = df1[col].unique()
    list_names2 = df2[col].unique()
    ### Merge mapping construction based on id (name) column
    # Find all similar names in df2 compared to df1 (missing names will be None)
    for c in _tqdm(list_names1, total=len(df1[col].unique()), desc='MERGE'):
        found = False
        if dist_threshold <= 0.0 and dist_words_threshold <= 0.0:
            # No fuzzy matching, we simply compute equality
            if c in list_names2:
                dmerge.append( (c, c) )
                found = True
        else:
            # Fuzzy matching
            for cd in list_names2:
                if not cd:
                    continue
                # Clean up the names
                name1 = cleanup_name(replace_buggy_accents(c))
                name2 = cleanup_name(replace_buggy_accents(cd))
                # Compute similarity
                testsim1 = distance.nlevenshtein(name1, name2, method=1) <= dist_threshold  # character-wise distance on the whole name
                testsim2 = distance_jaccard_words_split(name1, name2, partial=False, norm=True, dist=dist_threshold) <= dist_words_threshold  # word-wise distance
                if (mode==0 and (testsim1 or testsim2)) or (mode==1 and testsim1 and testsim2): # use shortest distance with normalized levenshtein
                    # Found a similar name in both df, add the names
                    dmerge.append( (c, cd) )
                    found = True
        # Did not find any similar name, add as None
        if not found:
            dmerge.append( (c, None) )
    # Find all names missing in df1 compared to df2
    missing = [(None, x) for x in list(set(list_names2) - set([y for _,y in dmerge if y is not None]))]
    dmerge.extend(missing)
    # Convert to a dataframe
    dmerge = pd.DataFrame(dmerge, columns=[col, col+'2'])
    # Sanity check
    if not skip_sanity:
        for n in list_names2:
            try:
                assert dmerge[dmerge[col+'2'] == n].count().max() <= 1
            except AssertionError as exc:
                raise AssertionError('Conflict found: a subject has more than one mapping! Subject: %s %s' % (n, dmerge[dmerge[col+'2'] == n]))
        for n in list_names1:
            try:
                assert dmerge[dmerge[col] == n].count().max() <= 1
            except AssertionError as exc:
                raise AssertionError('Conflict found: a subject has more than one mapping! Subject: %s %s' % (n, dmerge[dmerge[col] == n]))
    ### Mapping finished
    if not returnmerged:
        # Return merge mapping result!
        return dmerge
    else:
        ### Return not only the ID merge result but a unified DataFrame merging both whole databases (ie, all columns)
        if keep_nulls is True:
            # Recopy empty matchs from the other database (so that we don't lose them after the final merge)
            dmerge.loc[dmerge[col].isnull(), col] = dmerge[col+'2']
            dmerge.loc[dmerge[col].isnull(), col+'2'] = dmerge[col]
        elif keep_nulls is False:
            dmerge = dmerge.dropna(how='any')
        elif keep_nulls == 1:
            dmerge = dmerge.dropna(how='any', subset=[col+'2'])
        elif keep_nulls == 2:
            dmerge = dmerge.dropna(how='any', subset=[col])
        # Remap IDs
        df2 = df_remap_names(df2, dmerge, col, col+'2', keep_nulls=keep_nulls)
        del df2['index']
        # Merging databases
        if keycol is None:
            # Simple merging on one key column (name usually)
            # Concatenate all rows into one per gupi
            df1 = df_concatenate_all_but(df1, col, setindex=False)
            df2 = df_concatenate_all_but(df2, col, setindex=False)
            # Final merge of all columns
            dfinal = pd.merge(df1, df2, how='outer', on=col)
        else:
            # More complex merging on multiple key columns
            # Concatenate all rows into one per key columns (ie, we aggregate on the key columns)
            df1 = df_concatenate_all_but(df1, keycol[0].keys(), setindex=False)
            df2 = df_concatenate_all_but(df2, keycol[1].keys(), setindex=False)
            # Preprocessing key columns with specific datatypes (eg, datetime), else they won't be comparable across the two input DataFrames
            for df, kcol in zip([df1, df2], keycol):  # for each dataframe and the corresponding key columns list
                for colname, coltype in kcol.items():  # loop through each key column for this dataframe
                    # datetime type: will convert the column into a datetime format by interpreting it given the formatting provided by user in the following format, separated by a '|': 'datetime|%formatting%here'
                    if coltype.startswith('datetime'):
                        df = convert_to_datetype(df, colname, coltype.split('|')[1])
                    # other types: we do nothing (the id type is already taken care of at the beginning of the function, the rest is undefined at the moment)
            # Final merge of all columns
            dfinal = pd.merge(df1, df2, how='outer', left_on=keycol[0].keys(), right_on=keycol[1].keys(), **kwargs)
            # Filling gaps by squashing per subject id and trying to fill the missing fields from another row of the same subject where the information is present
            if fillna:
                # Generate an aggregate only based on id
                dfinal_agg = dfinal.drop(columns=[colname for kcol in keycol for colname, coltype in kcol.items() if coltype != 'id']).fillna('').groupby(by=col, sort=False).agg(concat_vals_unique)
                # Fill nan values from other rows of the same subject, by using pandas.combine_first() function
                dfinal = dfinal.set_index(col).combine_first(dfinal_agg.reset_index().set_index(col)).reset_index()
            # Create new columns merging key columns info (similarly to names), this can be useful for further merge (ie, to use one merged key column instead of two different)
            for kcol1, kcol2 in zip(keycol[0].items(), keycol[1].items()):
                col1name, col1type = kcol1
                col2name, col2type = kcol2
                if col1type != 'id':
                    colcombined = col1name+' + '+col2name
                    # Copy from first dataframe's key column values
                    dfinal[col1name+' + '+col2name] = dfinal[col1name]
                    # Copy datatype from the original dataframe. Since pandas.merge() loses the datatype info of the columns after merging, we need to use the original dataframes where we already converted the key columns to the correct datatypes: https://stackoverflow.com/questions/29280393/python-pandas-merge-loses-categorical-columns
                    dfinal[col1name+' + '+col2name].astype(df1[col1name].dtype, inplace=True)
                    # Finally, where there is an empty value, copy from the second dataframe's (from the corresponding key column)
                    dfinal.loc[dfinal[col1name].isnull(), colcombined] = dfinal[col2name]
        # Keep log of original names from both databases, by creating other columns "_altx_orig", "_altx_orig2" and "_anyx" to store the name from 2nd database and create a column with any name from first db or second db
        for x in range(1000):
            # If we do multiple merge, we will have multiple name_alt columns: name_alt0, name_alt1, etc
            if not (col+'_alt%i' % (x+1)) in dfinal.columns:
                # Rename the name column from the 2nd database
                dfinal.insert(1, (col+'_alt%i_orig' % (x+1)), dfinal[col+'_orig']) # insert the column just after 'name' for ergonomy
                dfinal.insert(2, (col+'_alt%i_orig2' % (x+1)), dfinal[col+'_orig2'])

                # Finally delete the useless column (that we copied over to name_altx)
                del dfinal[col+'_orig']
                del dfinal[col+'_orig2']

                # Finish! We found an non existent alt%i number so we can just stop here
                break
        # Return both the merge mapping and the final merged database
        return (dmerge, dfinal)

def remove_strings_from_df(df):
    """Remove all strings from a dataframe and replace by nan and convert to float (can supply a subset of columns)"""
    # Courtesy of instant: https://stackoverflow.com/a/41941267/1121352
    def isnumber(x):
        try:
            float(x)
            return True
        except:
            return False
    return df[df.applymap(isnumber)].applymap(float)

def concat_vals(x):
    """Concatenate after a groupby values in a list, and keep the same order (except if all values are the same or null, then return a singleton). This is similar to groupby(col).agg(list) but this function returns a singleton whenever possible (for readability)."""
    try:
        x = list(x)
        if len(sort_and_deduplicate(x)) == 1:
            x = x[0]
        elif len([y for y in x if (isinstance(y, list) or not pd.isnull(y)) and (hasattr(y, '__len__') and len(y) > 0)]) == 0:
            x = None
    except Exception as exc:
        # Warning: pd.groupby().agg(concat_vals) can drop columns without a notice if an exception happens during the execution of the function
        print('Warning: aggregation using concat_vals() met with an exception, at least one column will be dropped!')
        print(exc)
        raise
    return x

def concat_vals_unique(x):
    """Concatenate after a groupby values in a list (if not null and not unique, else return the singleton value)"""
    try:
        x = list(sort_and_deduplicate([y for y in x if (isinstance(y, list) or not pd.isnull(y)) and (hasattr(y, '__len__') and len(y) > 0)]))
        if len(x) == 1:
            x = x[0]
        elif len(x) == 0:
            x = None
    except Exception as exc:
        # Warning: pd.groupby().agg(concat_vals) can drop columns without a notice if an exception happens during the execution of the function
        print('Warning: aggregation using concat_vals_unique() met with an exception, at least one column will be dropped!')
        print(exc)
        raise
    return x

def uniq(lst):
    # From https://stackoverflow.com/questions/13464152/typeerror-unhashable-type-list-when-using-built-in-set-function
    last = object()
    for item in lst:
        if item == last:
            continue
        yield item
        last = item

def sort_and_deduplicate(l):
    """Alternative to using set(list()) with no computational overhead, since set() is limited to hashable types (hence not lists)"""
    # From https://stackoverflow.com/questions/13464152/typeerror-unhashable-type-list-when-using-built-in-set-function
    return list(uniq(sorted(l, reverse=True)))

def concat_strings(serie, prefix='', sep=''):
    """Concatenate multiple columns as one string. Can add a prefix to make sure Pandas saves the column as a string (and does not trim leading 0)"""
    return prefix+sep.join([x if isinstance(x, str) else str(int(x)) if not pd.isnull(x) else '' for x in serie])

def find_columns_matching(df, L, startswith=False):
    """Find all columns of a DataFrame matching one string of the given list (case insensitive)"""
    if isinstance(L, str):
        L = [L]
    L = [l.lower() for l in L]
    matching_columns = []
    for col in df.columns:
        if (not startswith and any(s in col.lower() for s in L)) or \
            (startswith and any(col.lower().startswith(s) for s in L)):
            matching_columns.append(col)
    return matching_columns

def reorder_cols_df(df, cols):
    """Reorder the columns of a DataFrame to start with the provided list of columns"""
    cols_without = df.columns.tolist()
    for col in cols:
        cols_without.remove(col)
    return df[cols + cols_without]

def df_remap_names(df, dfremap, col='name', col2='name2', keep_nulls=False):
    """Remap names in a dataframe using a remapping list (ie, a dataframe with two names columns)"""
    def replace_nonnull_df(x, repmap):
        replacement = repmap[x]
        return replacement if replacement is not None else x
    repmap = dfremap.set_index(col2)[col].to_dict()
    df2 = df.copy().reset_index()
    if keep_nulls:
        # Much faster but if there are nulls they will be replaced
        df2[col] = df2[col].map(repmap)
    else:
        # Slower but remap only if the remap is not null
        df2[col] = df2[col].apply(lambda x: replace_nonnull_df(x, repmap))
    return df2

def convert_to_datetype(df, col, dtformat, **kwargs):
    """Convert a column of a dataframe to date type with the given format"""
    if not df.index.name is None:
        df = df.reset_index()
    try:
        df[col] = pd.to_datetime(df[col], format=dtformat, **kwargs)
    except Exception as exc:
        print('Warning: cannot convert column %s as datetype using pandas.to_datetime() and formatting %s and supplied format, falling back to fuzzy matching date format (this might introduce buggy dates, you should check manually afterwards)...' % (col, dtformat))
        df = df_date_clean(df, col)
    return df

def df_drop_duplicated_index(df):
    """Drop all duplicated indices in a dataframe or series"""
    return df[~df.index.duplicated(keep='first')]

def cleanup_name_df(cf, col='name'):
    """Cleanup the name field of a dataframe"""
    cf[col] = cf[col].apply(lambda name: cleanup_name(name))
    return cf
    #for c in cf.itertuples():  # DEPRECATED: itertuples() is limited to 255 columns in Python < 3.7, prefer to avoid this approach
    #    try:
    #        cf.loc[c.Index, 'name'] = cleanup_name(c.name)
    #    except Exception as exc:
    #        print("An error occurred while cleaning up names in the provided dataframe, please check the following lines which might be the culprit:")
    #        print(cf[cf['name'].isnull()])
    #        raise
    #return cf

def cleanup_name_customregex(cname, customregex=None, returnmatches=False):
    """Cleanup the input name given a custom dictionary of regular expressions (format of customregex: a dict like {'regex-pattern': 'replacement'}"""
    if customregex is None:
        customregex = {'_': ' ',
                       'repos': '',
                       'ecg': '',
                       '[0-9]+': '',
                      }
    matches = set()
    # For each pattern
    for pattern, replacement in customregex.iteritems():
        # First try to see if there is a match and store it if yes
        if returnmatches:
            m = re.search(pattern, cname, flags=re.I)
            if m:
                matches.add(m.group(0))
        # Then replace the pattern found
        cname = re.sub(pattern, replacement, cname, flags=re.I)

    # Return both the cleaned name and matches
    if returnmatches:
        return (cname, matches)
    # Return just the cleaned name
    else:
        return cname

def cleanup_name_customregex_df(cf, customregex=None):
    """Cleanup the name fields of a dataframe given a custom dictionary of regular expressions (format of customregex: a dict like {'regex-pattern': 'replacement'}"""
    cf['name'] = cf['name'].apply(lambda name: cleanup_name_customregex(name, customregex))
    return cf

def compute_names_distance_matrix(list1, list2, dist_threshold_letters=0.2, dist_threshold_words=0.2, dist_threshold_words_norm=True, dist_minlength=0):
    """Find all similar items in two lists that are below a specified distance threshold (using both letters- and words- levenshtein distances). This is different from disambiguate_names() which is working on a single dataframe (trying to uniformize the names (mis)spellings).
    Note: this works less efficiently than merge_two_df(), you should use the latter."""
    dist_matches = {}
    for subj in _tqdm(list1, total=len(list1), desc='MERGE'):
        found = False
        subj = cleanup_name(replace_buggy_accents(subj))
        for c in list2:
            c = cleanup_name(replace_buggy_accents(c))
            # use shortest distance with either normalized levenshtein distance or non-normalized levenshtein distance
            if distance.nlevenshtein(subj, c, method=1) <= dist_threshold_letters or (
                (dist_threshold_words_norm is not None and distance_jaccard_words_split(subj, c, partial=False, norm=dist_threshold_words_norm, dist=dist_threshold_letters, minlength=dist_minlength) <= dist_threshold_words) or
                (dist_threshold_words_norm is None and distance_jaccard_words_split(subj, c, partial=False, norm=dist_threshold_words_norm, dist=dist_threshold_letters, minlength=dist_minlength) >= dist_threshold_words)
                ):
                if subj not in dist_matches:
                    dist_matches[subj] = []
                dist_matches[subj].append(c)
                found = True
        if not found:
            dist_matches[subj] = None
    # Remove duplicate values (ie, csv names)
    dist_matches = {k: (list(set(v)) if v else v) for k, v in dist_matches.items()}
    return dist_matches

def disambiguate_names(cf, dist_threshold=0.2, verbose=False): # TODO: replace by the updated compute_names_distance_matrix() function?
    """Disambiguate names in a single dataframe, in other words finds all the different (mis)spellings of the same person's name and uniformize them all, so that we can easily find all the records pertaining to a single subject. This is different from compute_names_distance_matrix() function which works on two different dataframes."""
    cf = cf.assign(alt_names='')  # create new column alt_names with empty values by default
    for c in cf.itertuples(): # TODO: does not work with more than 255 columns!
        for c2 in cf.ix[c.Index+1:,:].itertuples():
            if c.name != c2.name and \
            (distance.nlevenshtein(c.name, c2.name, method=1) <= dist_threshold or distance_jaccard_words_split(c2.name, c.name, partial=False, norm=True, dist=dist_threshold) <= dist_threshold): # use shortest distance with normalized levenshtein
                if verbose:
                    print(c.name, c2.name, c2.Index, distance.nlevenshtein(c.name, c2.name, method=1))
                # Replace the name of the second entry with the name of the first entry
                cf.ix[c2.Index, 'name'] = c.name
                # Add the other name as an alternative name, just in case we did a mistake for example
                cf.ix[c.Index, 'alt_names'] = cf.ix[c.Index, 'alt_names'] + '/' + c2.name if cf.ix[c.Index, 'alt_names'] else c2.name
    return cf

def df_concatenate_all_but(cf, col, setindex=False):
    """Make sure each id (in col) is unique, else concatenate all other rows for each id into one row.
    col can either be a string for a single column name, or a list of column names to use for the aggregation."""
    cf.loc[:,col] = cf.loc[:,col].fillna(value='')  # fill nan values with placeholder to avoid losing these rows, particularly with multiple columns as keys of groupby, this can lead to mysterious loss of rows. Indeed, pandas drops any row where the groupby key columns have a nan or nat value (in any of the key columns! Even if other key columns are filled!). There is currently no option to disable this behavior. See https://github.com/pandas-dev/pandas/issues/3729 and https://stackoverflow.com/questions/18429491/groupby-columns-with-nan-missing-values for more info.
    cf = cf.reset_index().groupby(col, sort=False).agg(concat_vals)  # groupby the key columns and aggregate by concatenating duplicated values (using our custom function concat_vals)
    cf.reset_index(inplace=True)
    if setindex:
        cf.set_index(col, inplace=True)
    return cf

def df_to_unicode(df, cols=None, failsafe_encoding='iso-8859-1', skip_errors=False):
    """Ensure unicode encoding for all strings in the specified columns of a dataframe.
    If cols=None, will walk through all columns.
    If failing to convert to unicode, will use failsafe_encoding to attempt to decode.
    If skip_errors=True, the unicode encoding will be forced by skipping undecodable characters (errors='ignore').
    """
    if cols is None:
        cols = df.columns
    for col in cols:
        for idx in df[col].index:
            if isinstance(df.loc[idx,col], basestring):
                try:
                    df.loc[idx,col] = unicode(df.loc[idx,col])
                except UnicodeDecodeError as exc:
                    try:
                        df.loc[idx,col] = df.loc[idx,col].decode(failsafe_encoding)
                    except UnicodeDecodeError as exc2:
                        if skip_errors:
                            df.loc[idx,col] = unicode(df.loc[idx,col], errors='ignore')
                        else:
                            raise
    return df

def df_to_unicode_fast(df, cols=None, skip_errors=False):
    """Ensure unicode encoding for all strings in the specified columns of a dataframe, by replacing non recognized characters by ascii equivalents. Also ensures that columns names are correctly decodable as unicode if cols=None.
    If cols=None, will walk through all columns.
    If failing to convert to unicode, will use failsafe_encoding to attempt to decode.
    If skip_errors=True, the unicode encoding will be forced by skipping undecodable characters (errors='ignore').
    """
    if cols is None:
        cols = df.columns
        # Ensure column names are unicode
        df.columns = [unicode(cleanup_name(x, normalize=False, clean_nonletters=False), errors='ignore') for x in df.columns]
    if skip_errors:
        serrors = 'ignore'
    else:
        serrors = 'strict'
    for col in cols:
        try:
            df.loc[:, col] = df.loc[:, col].apply(lambda x: unicode(cleanup_name(x, normalize=False, clean_nonletters=False), errors=serrors) if isinstance(x, basestring) else x)
            df.loc[:, col] = df.loc[:, col].astype('unicode')
            #df[col] = df[col].map(lambda x: x.encode('unicode-escape').decode('utf-8'))
        except Exception as exc:
            pass
    return df

def df_literal_eval(x):
    """Evaluate each string cell of a DataFrame as if it was a Python object, and return the Python object"""
    try:
        return(ast.literal_eval(x))
    except (SyntaxError, ValueError):
        return x

def df_cols_lower(df, col='name'):
    """Find in a DataFrame any column matching the col argument in lowercase and rename all found columns to lowercase"""
    # Find and rename any column "Name" or "NAME" to lowercase "name"
    namecols = df.columns[[True if x.lower() == col.lower() else False for x in df.columns]]
    if len(namecols) > 0:
        df = df.rename(columns={x: x.lower() for x in namecols})
    return df

def date_fr2en(s):
    """Convert french month names into english so that dateutil.parse works"""
    if isinstance(s, basestring):
        s = s.lower()
        rep = {
            'jan\w+': 'jan',
            'fe\w+': 'feb',
            'mar\w+': 'march',
            'av\w+': 'april',
            'mai\w+': 'may',
            'juin\w+': 'june',
            'juil\w+': 'july',
            'ao\w+': 'august',
            'se\w+': 'september',
            'oc\w+': 'october',
            'no\w+': 'november',
            'de\w+': 'december',
        }
        for m, r in rep.items():
            s = re.sub(m, r, s)
    return s

def date_cleanchar(s):
    """Clean a date from any non useful character (else dateutil_parser will fail, eg with a '?')"""
    if isinstance(s, basestring):
        s = s.lower()
        res = re.findall('[\d/-:\s]+', s, re.UNICODE)
        if res:
            return '-'.join(res)
        else:
            return None
    else:
        return s

def date_clean(s):
    """Clean the provided string and parse as a date using dateutil.parser fuzzy matching (alternative to pd.to_datetime()). Should be used with df[col].apply(df_date_clean)."""
    if pd.isnull(s):
        return None
    else:
        # Clean non date characters (might choke the date parser)
        cleaned_date = date_fr2en(date_cleanchar(s))
        if not cleaned_date:
            return None
        else:
            try:
                # Try to parse with formatting with day first
                return dateutil_parser.parse(cleaned_date, dayfirst=True, fuzzy=True)
            except ValueError as exc:
                # If failed, try with year first
                try:
                    m = re.search('\d+', s, re.UNICODE)
                    if len(m.group(0)) == 4:
                        return dateutil_parser.parse(cleaned_date, yearfirst=True, fuzzy=True)
                    else:
                        raise
                except Exception as exc:
                    # Else we print an error but we pass (we just don't use this date)
                    print('Warning: Failed parsing this date: %s' % s)
                    return None

def df_date_clean(df, col):
    """Apply fuzzy date cleaning (and datetype conversion) to a dataframe's column"""
    df[col] = df[col].apply(date_clean)
    return df
