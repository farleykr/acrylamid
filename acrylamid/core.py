#!/usr/bin/env python
# -*- encoding: utf-8 -*-
#
# Copyright 2011 posativ <info@posativ.org>. All rights reserved.
# License: BSD Style, 2 clauses. see acrylamid.py

import logging
import os
import fnmatch

from acrylamid.utils import EntryList, FileEntry
log = logging.getLogger('acrylamid.core')


def handle(request):
    """This will prepare the whole thing. Dir-walks through content dir and
    try to get the timestamp (fallback to '%d.%m.%Y, %H:%M' parsing, or even
    worse: mtime). return entrylist reverse sorted by date."""

    conf = request['conf']
    env = request['env']
    env['tt_env'].filters['safeslug'] = False
    env['tt_env'].filters['tagify'] = False

    request['entrylist'] = EntryList(filelist(request))
    request['entrylist'].sort(key=lambda k: k.date, reverse=True)
    return request


def filelist(request):
    """gathering all entries in entries_dir except entries_ignore via fnmatch."""

    conf = request['conf']

    flist = []
    for root, dirs, files in os.walk(conf['entries_dir']):
        for f in files:
            path = os.path.join(root, f)
            fn = filter(lambda p: fnmatch.fnmatch(path, os.path.join(conf['entries_dir'], p)),
                        conf.get('entries_ignore', []))
            if not fn:
                flist.append(path)

    entrylist = [FileEntry(e, conf) for e in flist]
    return entrylist
