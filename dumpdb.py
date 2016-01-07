#!/usr/bin/python

import sys
import bsddb

if len(sys.argv) < 2:
	print 'Usage : ' + __file__ + ' file1 file2 ...'
	sys.exit()


for filename in sys.argv[1:]:
	print '\ndump ' + filename + ':'
	db = bsddb.btopen(filename, 'r')
	for k, v in db.iteritems():
		print '\t', k, v
	
print ''
