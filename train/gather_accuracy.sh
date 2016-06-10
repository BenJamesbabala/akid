#!/bin/bash
# Copyright 2016
#
# Filename: gather_accuracy.sh
# Author: Shuai
# Contact: lishuai918@gmail.com
# Created: Fri Mar 25 14:20:30 2016 (+0800)
# Package-Requires: ()
#
#
# Code:

usage () {
    printf "This script gathers training accuracy from all tensorflow event
files in the sub folders one level deeper under a given folder.

The sub folder name will be at the top of the accuracy output, so it is
suggested to give an informative name to the sub folder.
"
}

if [ $# != 1 ]
then
   usage
fi

LOG_DIR=$(readlink -f $1)
OUTPUT_FILENAME="acc_summary.txt"

echo "Accuracy Summary" > $OUTPUT_FILENAME

IFS='|'
for log_file in $LOG_DIR/*/event*;
do
    echo $log_file >> $OUTPUT_FILENAME
    echo -e '' >> $OUTPUT_FILENAME
    get_accuracy.py $log_file >> $OUTPUT_FILENAME
    echo -e '\n' >> $OUTPUT_FILENAME
done

#
# gather_accuracy.sh ends here
