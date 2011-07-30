#!/usr/bin/env python
# -*- encoding: utf-8 -*-
#
# Copyright 2011 posativ <info@posativ.org>. All rights reserved.
# License: BSD Style, 2 clauses. see lilith.py

import logging
import os
import re
import fnmatch
from datetime import datetime

from lilith import FileEntry
from lilith import tools

from jinja2 import Template

log = logging.getLogger('lilith.core')

def start(request):
    """this loads entry.html and main.html into data and does a little
    preprocessing: {{ include: identifier }} will be replaced by the
    corresponding identifier in request._env if exist else empty string."""
    
    from collections import defaultdict
    
    conf = request._config
    env = request._env
    data = request._data
    regex = re.compile('{{\s*include:\s+(\w+)\s*}}')
    entry = open(os.path.join(conf['layout_dir'], 'entry.html')).read()
    main = open(os.path.join(conf['layout_dir'], 'main.html')).read()
    
    d = defaultdict(str)
    d.update(env)
    data['tt_entry'] = re.sub(regex, lambda m: d[m.group(1)], entry)
    data['tt_main'] = re.sub(regex, lambda m: d[m.group(1)], main)
    
    return request

def filelist(request):
    """This is the default handler for getting entries.  It takes the
    request object in and figures out which entries bases on the default
    behavior that we want to show and generates a list of EntryBase
    subclass objects which it returns.
    
    Arguments:
    args -- dict containing the incoming Request object
    
    Returns the content we want to render"""
    
    data = request._data
    conf = request._config
    
    filelist = []
    for root, dirs, files in os.walk(conf['entries_dir']):
        for file in files:
            path = os.path.join(root, file)
            fn = filter(lambda p: fnmatch.fnmatch(path, os.path.join(conf['entries_dir'], p)),
                        conf.get('entries_ignore', []))
            if not fn:
                filelist.append(path)
    
    # save last mtimes
    mtimes = {}
    new = []
    try:
       for line in open('.mtimes'):
           timestamp, path = line.split('\t')
           mtimes[path.strip()] = timestamp
    except OSError:
       pass

    for i, path in enumerate(filelist[:]):
       if os.path.getmtime(path) == mtimes.get(path, 0):
           pass
       else:
           new.append(path)
           mtimes[path] = os.path.getmtime(path)

    if len(new) > 0:
       f = open('.mtimes', 'w')
       for key in sorted(mtimes.keys()):
           f.write('{0}\t{1}\n'.format(key, mtimes[key]))
       f.close()

    entry_list = [FileEntry(request, e, new=(e in new)) for e in filelist]
    data['entry_list'] = entry_list
  
    return request
  
def filestat(request):
    """Sets an alternative timestamp specified in yaml header."""
    
    conf = request._config
    entry_list = request._data['entry_list']
    
    for i in range(len(entry_list)):
        if entry_list[i].has_key('date'):
            timestamp = time.strptime(entry_list[i]['date'],
                                conf.get('strptime', '%d.%m.%Y, %H:%M'))
            timestamp = time.mktime(timestamp)
            entry_list[i].date = datetime.fromtimestamp(timestamp)
        else:
            entry_list[i]['date'] = entry_list[i]._date
            log.warn("using mtime from %s" % entry_list[i])
    return request
    
def sortlist(request):
    """sort list by date"""

    entry_list = request._data['entry_list']
    entry_list.sort(key=lambda k: k.date, reverse=True)
    return request

def entryparser(request):
    """Applies:
        - cb_preformat
        - cb_format
        - cb_postformat"""
    
    entry = request['entry']
    
    entry = tools.run_callback(
            'preformat',
            {'entry': entry, 'config': request['config']},
            defaultfunc=preformat)['entry']

    entry = tools.run_callback(
            'format',
            {'entry': entry, 'config': request['config']},
            defaultfunc=format)['entry']
        
    entry = tools.run_callback(
            'postformat',
            {'entry': entry, 'config': request['config']})['entry']
    
    return entry
    
def preformat(request):
    """joins content from file (stored as list of strings)"""
    
    entry = request['entry']
    entry['body'] = ''.join(entry['story'])
    return request

def format(request):
    """Apply markup using Post.parser."""
    
    entry = request['entry']
    conf = request['config']
    
    parser = entry.get('parser', conf.get('parser', 'plain'))
    
    if parser.lower() in ['markdown', 'mkdown', 'md']:
        from markdown import markdown
        entry['body'] = markdown(entry['body'],
                        extensions=['codehilite(css_class=highlight)'])
        return request
    
    elif parser.lower() in ['restructuredtest', 'rst', 'rest']:                
        from docutils import nodes
        from docutils.parsers.rst import directives, Directive
        from docutils.core import publish_parts
        
        # Set to True if you want inline CSS styles instead of classes
        INLINESTYLES = False
        
        from pygments.formatters import HtmlFormatter
        
        # The default formatter
        DEFAULT = HtmlFormatter(noclasses=INLINESTYLES)
        
        
        from docutils import nodes
        from docutils.parsers.rst import directives, Directive
        
        from pygments import highlight
        from pygments.lexers import get_lexer_by_name, TextLexer
        
        class Pygments(Directive):
            """ Source code syntax hightlighting.
            """
            required_arguments = 1
            optional_arguments = 0
            final_argument_whitespace = True
            option_spec = dict([(key, directives.flag) for key in {}])
            has_content = True
    
            def run(self):
                self.assert_has_content()
                try:
                    lexer = get_lexer_by_name(self.arguments[0])
                except ValueError:
                    # no lexer found - use the text one instead of an exception
                    lexer = TextLexer()
                # take an arbitrary option if more than one is given
                formatter = self.options and VARIANTS[self.options.keys()[0]] or DEFAULT
                parsed = highlight(u'\n'.join(self.content), lexer, formatter)
                return [nodes.raw('', parsed, format='html')]
        
        directives.register_directive('sourcecode', Pygments)
        initial_header_level = 1
        transform_doctitle = 0
        settings = {
            'initial_header_level': initial_header_level,
            'doctitle_xform': transform_doctitle
            }
        parts = publish_parts(
            entry['body'], writer_name='html', settings_overrides=settings)
        entry['body'] = parts['body'].encode('utf-8')
        return request
    else:
        return request

def prepare(request):
    """Sets a few required keys in FileEntry.
    
    required:
    safe_title -- used as directory name
    url -- permalink
    id -- atom conform id: http://diveintomark.org/archives/2004/05/28/howto-atom-id
    """
    conf = request._config
    data = request._data
    
    for i, entry in enumerate(data['entry_list']):
        safe_title = tools.safe_title(entry['title'])
        url = '/' + str(entry.date.year) + '/' + safe_title + '/'
        id = 'tag:' + re.sub('https?://', '', conf.get('www_root', '')).strip('/') \
             + ',' + entry.date.strftime('%Y-%m-%d') + ':' \
             + '/' + str(entry.date.year) +  '/' + safe_title
        item = data['entry_list'][i]
        if not 'safe_title' in item:
            item['safe_title'] = safe_title
        if not 'url' in item:
            item['url'] = url
        if not 'id' in item:
            item['id'] = id
    
    return request
    
def item(request):
    """Creates single full-length entry.  Looks like
    http://yourblog.org/year/title/(index.html).
    
    required:
    entry.html -- layout of Post's entry
    main.html -- layout of the website
    """
    conf = request._config
    env = request._env
    data = request._data
    
    tt_entry = Template(data['tt_entry'])
    tt_main = Template(data['tt_main'])

    # last preparations
    request = tools.run_callback(
                'preitem',
                request)
    
    for entry in data['entry_list']:
        
        html = tools.render(tt_main, conf, env, type='item',
                            entry_list=tools.render(tt_entry, conf, env,
                                            entry, type='item') )
        
        directory = os.path.join(conf['output_dir'],
                         str(entry.date.year),
                         entry.safe_title)
        path = os.path.join(directory, 'index.html')
        tools.mk_file(html, entry, path)
        
    request = tools.run_callback(
                'postitem',
                request)
    
    return request

def page(request):
    """Creates nicely paged listing of your posts.  First “Page” is the
    index.hml used to have this nice url: http://yourblog.com/ with a recent
    list of your (e.g. summarized) Posts. Other pages are enumerated to /page/n+1
    
    required:
    items_per_page -- posts displayed per page (defaults to 6)
    entry.html -- layout of Post's entry
    main.html -- layout of the website
    """
    conf = request._config
    env = request._env
    data = request._data
    ipp = conf.get('items_per_page', 6)
    
    # last preparations
    request = tools.run_callback(
                'prepage',
                request)
        
    tt_entry = Template(data['tt_entry'])
    tt_main = Template(data['tt_main'])
            
    entry_list = [tools.render(tt_entry, conf, env, entry, type="page")
                    for entry in data['entry_list']]
                
    for i, mem in enumerate([entry_list[x*ipp:(x+1)*ipp]
                                for x in range(len(entry_list)/ipp+1)] ):
                                    
        html = tools.render(tt_main, conf, env, type='page', page=i+1,
                    entry_list='\n'.join(mem), num_entries=len(entry_list))
        directory = os.path.join(conf['output_dir'],
                         '' if i == 0 else 'page/%s' % (i+1))
        path = os.path.join(directory, 'index.html')
        tools.mk_file(html, {'title': 'page/%s' % (i+1)}, path)
    
    request = tools.run_callback(
                'postpage',
                request)
    
    return request