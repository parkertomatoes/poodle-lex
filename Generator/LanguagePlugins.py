# Copyright (C) 2014 Parker Michaels
# 
# Permission is hereby granted, free of charge, to any person obtaining a 
# copy of this software and associated documentation files (the "Software"), 
# to deal in the Software without restriction, including without limitation 
# the rights to use, copy, modify, merge, publish, distribute, sublicense, 
# and/or sell copies of the Software, and to permit persons to whom the 
# Software is furnished to do so, subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in 
# all copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR 
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, 
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE 
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER 
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING 
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER 
# DEALINGS IN THE SOFTWARE.

import Emitter
from Emitter.PluginTemplate import PluginTemplate
import re
import json
import os.path
import random
import string
import imp
import sys
import textwrap
import types

class PluginOptions(object):
    def __init__(self):
        self.is_backtracking = False
        self.class_name = None
        self.namespace = None
        self.file_name = None
        
class Plugin(object):
    """
    Class representing a Poodle-Lex language emitter plug-in
    """
    def __init__(self, source_path, plugin_files_directory, dependencies, description): 
        self.source_path = source_path
        self.plugin_files_directory = plugin_files_directory
        self.description = description
        self.dependencies = dependencies
        self.module = None
        self.dependency_modules = {}
        
    def load(self):
        """
        Loads the plug-in and verifies the interface
        """
        for dependency in self.dependencies:
            with open(dependency, 'r') as f:
                module_name = os.path.splitext(os.path.basename(dependency))[0]
                path_template = "Generator.Emitter.language_plugin_dependency_%s_%s"
                module_path = path_template % (module_name, ''.join(random.choice(string.ascii_lowercase) for i in range(8)))
                self.dependency_modules[module_name] = imp.load_module(module_path, f, dependency, (".py", 'r', imp.PY_SOURCE))
        with open(self.source_path, 'r') as f:
            module_path = "Generator.Emitter.language_plugin_%s" % ''.join(random.choice(string.ascii_lowercase) for i in range(16))
            self.module = imp.load_module(module_path, f, self.source_path, (".py", 'r', imp.PY_SOURCE))
        if not hasattr(self.module, 'create_emitter') or not isinstance(self.module.create_emitter, types.FunctionType):
            raise Exception("Plug-in does not contain a 'create_emitter' function")
            
    def create(self, lexical_analyzer, plugin_options):
        """
        Creates a LanugageEmitter object from the plug-in
        """
        if self.module is None:
            raise Exception("Plug-in not loaded")
        emitter = self.module.create_emitter(lexical_analyzer, self.dependency_modules, plugin_options)
        if not issubclass(emitter.__class__, PluginTemplate):
            raise Exception("Plug-in interface did not return a class of the correct type")
        return emitter
        
def is_text(text):
    """
    Simple utility function to determine if an object is of type str or unicode
    """
    return isinstance(text, str) or isinstance(text, unicode)
    
def is_path(text, base_directory):
    """
    Simple utility function to determine if the object is an str, and represents a valid path
    @return: a string with the resolved path, or None if not a path
    """
    if is_text(text):
        if not os.path.isabs(text):
            path = os.path.join(base_directory, text)
        else:
            path = text
        if os.path.exists(path):
            return path
    return None
                            
        
def load(base_directory, file, encoding='utf-8'):
    """ 
    Loads a plug-in file and returns 
    @param base_directory: string specifying the root directory of the application
    @param file: a string specifying the plug-in specification file
    @param encoding: a string specifying the encoding of the plug-in specification file
    @return: dict mapping strings representing plug-in identifiers to Plugin objects
    """
    language_plugins = {}
    default_language = None
    with open(os.path.join(base_directory, file)) as f:
        plugin_file = json.load(f, encoding)
        if "Version" not in plugin_file or not isinstance(plugin_file["Version"], int) or plugin_file["Version"] != 1:
            raise Exception("Language plug-in file version not recognized")
        if "Default" not in plugin_file or not is_text(plugin_file["Default"]):
            raise Exception("Default language not specified")
        default_language = plugin_file["Default"]
        if "Plugins" not in plugin_file or not isinstance(plugin_file["Plugins"], dict):
            raise Exception("Plugin dictionary not found")
        for plugin_id in plugin_file["Plugins"]:
            if is_text and re.match("[a-zA-Z][a-zA-Z0-9_\-\+]*", plugin_id):
                valid = True
                plugin_paths = {}
                dependencies = []
                description = ""
                for plugin_attr in plugin_file["Plugins"][plugin_id]:
                    if is_text(plugin_attr) and plugin_attr in ("Source", "Files"):
                        plugin_paths[plugin_attr] = is_path(plugin_file["Plugins"][plugin_id][plugin_attr], base_directory)
                        if plugin_paths[plugin_attr] is None:
                            valid = False
                    elif plugin_attr == "Dependencies":
                        raw_dependencies = plugin_file["Plugins"][plugin_id][plugin_attr]
                        if not isinstance(raw_dependencies, list):
                            valid = False
                        dependencies = [is_path(i, base_directory) for i in raw_dependencies]
                        if any(i is None for i in dependencies):   
                            valid = False
                    elif plugin_attr == "Description":
                        if is_text(plugin_file["Plugins"][plugin_id][plugin_attr]):
                            description = plugin_file["Plugins"][plugin_id][plugin_attr]
                        else:
                            valid = False
                if "Source" not in plugin_paths or "Files" not in plugin_paths:
                    valid = False
                if valid:
                    language_plugins[plugin_id] = Plugin(
                        plugin_paths["Source"], 
                        plugin_paths["Files"], 
                        dependencies,
                        description)
       
        if len(language_plugins) == 0:
            raise Exception("No plugins found")
        if plugin_file["Default"] not in language_plugins:
            raise Exception("Default language is invalid")
    return language_plugins, default_language
    
def describe(base_folder, file, encoding):
    language_plugins, default_language = load(base_folder, file, encoding)
    left_column_size = len(max(language_plugins, key=lambda i: len(i))) + 1
    sys.stderr.write("Available output languages:\n")
    for language, plugin in language_plugins.iteritems():
        paragraph = textwrap.wrap(plugin.description, 76-left_column_size)
        sys.stderr.write("    %s%s%s\n" % (language, ' '*(left_column_size-len(language)), paragraph[0]))
        if len(paragraph) > 1:
            for line in paragraph[1:]:
                sys.stderr.write("    %s%s\n" % (' '*left_column_size, line))
    