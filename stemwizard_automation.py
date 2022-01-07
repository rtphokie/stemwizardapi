#!/usr/bin/env python3

from STEMWizard import STEMWizardAPI
import pandas as pd
import argparse

def stats(listname, df, filename, columns):
    print(f"created {filename}")
    for column in columns:
        print(f'\n{column.lower()}')
        c = df[f"{column.upper()}"].value_counts(dropna=False)
        p = df[f"{column.upper()}"].value_counts(dropna=False, normalize=True).mul(100).round(1)
        print(pd.concat([c, p], axis=1, keys=[listname, '%']))
    print()
    print(f"total {listname}: {df.shape[0]}")


def get_args():
    global args
    parser = argparse.ArgumentParser(description='synchronize with STEM Wizard')
    parser.add_argument('-student', help='gather student data', action='store_true')
    parser.add_argument('-judge', help='gather judge data', action='store_true')
    parser.add_argument('-volunteer', help='gather volunteer data', action='store_true')
    parser.add_argument('-files', help='fetch files and forms metadata', action='store_true')
    parser.add_argument('-download', help='download files and forms', action='store_true')
    parser.add_argument('--configfile', help='download files and forms', default='stemwizardapi.yaml')
    args = parser.parse_args()


if __name__ == '__main__':
    get_args()
    if args.volunteer:
        raise ValueError("volunteer automation not implemented")

    sw = STEMWizardAPI(configfile=args.configfile)
    if args.download:
        data = sw.student_status(fileinfo=True, download=False)
    elif args.judge:
        filename, df = sw.export_judge_list()
        stats('judges', df, filename, ['HIGHEST DEGREE ATTAINED', 'SPECIAL AWARD JUDGE',
                                       'CITY', 'ORGANIZATION / EMPLOYER', 'REGISTRATION STATUS'])
    elif args.student:
        filename, df = sw.export_student_list()
        stats('students', df, filename,  ['approval status',
                                          'payment status', 'final status'])


