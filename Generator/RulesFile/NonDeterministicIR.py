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

from Visitor import Visitor, Traverser
from SectionResolver import SectionResolver
from .. import Automata
from .. import Regex

class NonDeterministicIR(object):
    """
    Represents an intermediate representation of a rules file in 
    which all state machines have been reduced to non-deterministic
    finite automata
    @ivar sections: a dictionary with each key a string representing a qualified section
        name, and each value a Sectionobject representing a state machine.
    """
    
    class Section(object):
        """
        Represents a section in the intermediate representation
        @ivar rules: a list of Rule objects, each representing a rule in the section, in order of priority 
        """
        def __init__(self, rules=[], inherits=False, parent=None):
            self.rules = list(rules)
            self.inherits = inherits
            self.parent = parent
        
    class Rule(object):
        """
        Represents a rule in the intermediate representation
        @ivar id: a string identifying the name of the rule
        @ivar nfa: a NonDeterministicFinite object representing the NFA representation of rule's regular expression
        @ivar action: a string representing the action to take with the rule's token
        @ivar section_action: a tuple, with a string and Section object. The action can be 'enter', 
            'exit' or None. If the action is 'enter', the Section object represents the section into 
            which the lexical analyzer should enter after matching the rule.
        @ivar line_number: the line of the rules file where the rule was declared.
        """
        def __init__(self, id, nfa, action, section_action, line_number):
            self.id = id
            self.nfa = nfa
            self.action = action
            self.section_action = section_action
            self.line_number = line_number

    def __init__(self, root):
        # Build non-deterministic finite automata from AST node
        builder = NonDeterministicIR.Builder()
        traverser = Traverser(builder)
        root.accept(traverser)
        
        # Add metadata
        self.sections = builder.sections
        self.rule_ids = builder.rule_ids
        self.root = root.get_qualified_name()
        
    class Builder(Visitor):
        """
        Visitor which constructs a NonDeterministicIR object from an
        AST node.
        @ivar sections: array of sections
        @ivar rule_ids: dictionary of case-insensitiv rule ID strings to case-sensitive rule ID strings
        """
        def __init__(self):            
            self.current_ast_section = None
            self.current_ir_section = None
            self.sections = {}
            self.rule_ids = {}
                    
        def visit_section(self, section):
            # Resolve all imports that weren't found during validation
            for id, rule in section.all('future_import'):
                reservation = section.find('reservation', rule.id)
                if reservation is None:
                    rule.throw('reservation not found for imported rule')
                if rule.pattern is None:
                    if reservation[0].pattern is None:
                        rule.throw('pattern must be defined for imported rule if not defined by reservation rule')
                    rule.pattern = reservation[0].pattern
            self.current_ast_section = section
            parent_id = section.parent.get_qualified_name() if section.parent is not None else None
            self.current_ir_section = NonDeterministicIR.Section(inherits=section.inherits, parent=parent_id)
            self.sections[section.get_qualified_name()] = self.current_ir_section
            
        def leave_section(self, section):
            """
            Update the scope upon leaving a section
            """
            self.current_ast_section = section.parent
            if self.current_ast_section is not None:
                self.current_ir_section = self.sections[section.parent.get_qualified_name()]
            else:
                self.current_ir_section = None
        
        def visit_rule(self, rule):
            """
            Resolve section references and variables, compile the rule
            into an NFA, and add to the currently visited section.
            """
            current_ast_section = self.current_ast_section
            class DefineLookup(object):
                """
                Lookup table class to resolve variable definition names into regular expression objects
                """
                def __contains__(self, item_name):
                    return current_ast_section.find('define', item_name) is not None
                
                def __getitem__(self, item_name):
                    result = current_ast_section.find('define', item_name)
                    if result is None:
                        raise Exception("variable '{id}' not found".format(id=item_name))
                    return Regex.Parser(result[0].pattern.regex, result[0].pattern.is_case_insensitive).parse() 
                
            try:
            
                if 'reserve' not in rule.rule_action:
                    rule_id_lower = rule.id.lower () if rule.id is not None else None
                    regex = Regex.Parser(rule.pattern.regex, rule.pattern.is_case_insensitive).parse()
                    nfa = Automata.NonDeterministicFiniteBuilder.build(rule_id_lower, DefineLookup(), regex)
                    section_action = None
                    if rule.section_action is not None:
                        action, section = rule.section_action
                        if section is not None:
                            rule_section = SectionResolver.resolve(section, self.current_ast_section)
                            if rule_section is None:
                                raise Exception("section '{id}' not found".format(id=section.name))
                            section = rule_section.get_qualified_name()
                        section_action = (action, section)
                    rule_action = [i.lower() if i is not None else None for i in rule.rule_action]
                    ir_rule = NonDeterministicIR.Rule(rule.id, nfa, rule_action, section_action, rule.line_number)
                    self.current_ir_section.rules.append(ir_rule)
                    if rule.id is not None and rule_id_lower not in self.rule_ids:
                        self.rule_ids[rule.id] = rule.id
                    
            except Exception as e:
                if rule.id is None:
                    rule.throw("anonymous rule: {message}".format(message=str(e)))
                else:
                    rule.throw("rule '{id}': {message}".format(id=rule.id, message=str(e)))
                
        def get(self):
            """
            Return the sections that were compiled from the rules file
            """
            return self.sections
