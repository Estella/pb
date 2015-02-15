# -*- coding: utf-8 -*-
"""
    paste.views
    ~~~~~~~~~~~

    paste url routes and views.

    :copyright: Copyright (C) 2015 by the respective authors; see AUTHORS.
    :license: GPLv3, see LICENSE for details.
"""

from yaml import safe_dump
from uuid import UUID
from mimetypes import guess_type

from flask import Blueprint, Response, request, render_template, current_app, url_for
from jinja2 import Markup
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_all_lexers

from pb.paste import model, handler as _handler
from pb.util import highlight, redirect, request_content, id_url, publish_parts, any_url

paste = Blueprint('paste', __name__)

@paste.app_template_filter(name='rst')
def filter_rst(source):
    return Markup(publish_parts(source))

@paste.app_template_global()
def include_raw(filename):
    env = current_app.jinja_env
    source = current_app.jinja_loader.get_source(env, filename)[0]
    return Markup(source)

@paste.route('/')
def index():
    return Response(render_template("index.html"), mimetype='text/html')

@paste.route('/f')
def form():
    return Response(render_template("form.html"), mimetype='text/html')

@paste.route('/', methods=['POST'])
@paste.route('/<label:vanity>', methods=['POST'])
def post(vanity=None):
    content, filename = request_content()
    if not content:
        return "Nope.\n", 400

    cur = model.get_digest(content)
    if not cur.count():
        if vanity:
            label, _ = vanity
            paste = model.insert(content, label=label)
        elif request.form.get('p'):
            paste = model.insert(content, private=1)
        else:
            paste = model.insert(content)
        uuid = str(UUID(hex=paste['_id']))
    else:
        paste = cur.__next__()
        uuid = '<redacted>'

    url = any_url(paste, filename=filename)
    return redirect(url, safe_dump(dict(url=url, uuid=uuid), default_flow_style=False))

@paste.route('/<uuid:uuid>', methods=['PUT'])
def put(uuid):
    content, filename = request_content()
    if not content:
        return "Nope.\n", 400

    cur = model.get_digest(content)
    if cur.count():
        url = any_url(cur.__next__())
        return redirect(url, "Paste already exists.\n", 409)

    result = model.put(uuid, content)
    if result['n']:
        # FIXME: need to invalidate cache
        return "{} pastes updated.\n".format(result['n']), 200

    return "Not found.\n", 404

@paste.route('/<uuid:uuid>', methods=['DELETE'])
def delete(uuid):
    result = model.delete(uuid)
    if result['n']:
        # FIXME: need to invalidate cache
        return "{} pastes deleted.\n".format(result['n']), 200
    return "Not found.\n", 404

@paste.route('/<sid(length=8):sid>')
@paste.route('/<sid(length=8):sid>/<string(minlength=0):lexer>')
@paste.route('/<string(length=1):handler>/<sid(length=8):sid>')
@paste.route('/<sha1:sha1>')
@paste.route('/<sha1:sha1>/<string(minlength=0):lexer>')
@paste.route('/<string(length=1):handler>/<sha1:sha1>')
@paste.route('/<label:label>')
@paste.route('/<label:label>/<string(minlength=0):lexer>')
@paste.route('/<string(length=1):handler>/<label:label>')
def get(sid=None, sha1=None, label=None, lexer=None, handler=None):
    cur = None
    if sid:
        sid, name = sid
        cur = model.get_content(
            _id = {
                '$regex': '{}$'.format(sid)
            },
            private = {
                '$exists': False
            }
        )
    if sha1:
        digest, name = sha1
        cur = model.get_content(digest = digest).hint([('digest', 1)])
    if label:
        label, name = label
        cur = model.get_content(label = label).hint([('label', 1)])

    if not cur or not cur.count():
        return "Not found.\n", 404

    content = cur.__next__()['content']

    mimetype, _ = guess_type(name)

    if lexer != None:
        return highlight(content, lexer)
    if handler != None:
        return _handler.get(handler, content)
    if mimetype:
        return Response(content, mimetype=mimetype)

    return content

@paste.route('/s')
def stats():
    cur = model.get_stats()
    return safe_dump(dict(pastes=cur.count()), default_flow_style=False)

@paste.route('/static/highlight.css')
def highlight_css():
    css = HtmlFormatter().get_style_defs('.code')
    return Response(css, mimetype='text/css')

@paste.route('/l')
def list_lexers():
    lexers = '\n'.join(' '.join(i) for _, i, _, _ in get_all_lexers())
    return '{}\n'.format(lexers)
