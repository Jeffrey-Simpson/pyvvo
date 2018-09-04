"""
This module contains function to parse a GLM into a dictionary that can then be
modified and then exported to a modified glm

    parse(inputStr, filePath=True):
        Main function to parse in glm
    _tokenize_glm(inputStr, filePath=True):
        Helper function to parse glm
    _parse_token_list(tokenList):
        Helper function to parse glm
    sorted_write(inTree):
        Main function to write out glm
    _dict_to_string(inDict):
        Helper function to write out glm
    _gather_key_values(inDict, keyToAvoid):
        Helper function to write out glm


Adopted August 30, 2018 by Brandon Thayer (brandon.thayer@pnnl.gov)
Modified March 28, 2017 by Jacob Hansen (jacob.hansen@pnnl.gov)
Created October 27, 2014 by Ebony Mayhorn (ebony.mayhorn@pnnl.gov)

Copyright (c) 2018 Battelle Memorial Institute.  The Government retains
a paid-up nonexclusive, irrevocable worldwide license to reproduce,
prepare derivative works, perform publicly and display publicly by or
for the Government, including the right to distribute to other
Government contractors.
"""

import re
import warnings
from functools import reduce


def parse(input_str, file_path=True):
    """
    Parse a GLM into an omf.feeder tree. This is so we can walk the tree,
    change things in bulk, etc.

    Input can be a file path or GLM string.
    """

    tokens = _tokenize_glm(input_str, file_path)
    return _parse_token_list(tokens)


def _tokenize_glm(input_str, file_path=True):
    """ Turn a GLM file/string into a linked list of tokens.

    E.g. turn a string like this:
    clock {clockey valley;};
    object house {name myhouse; object ZIPload {inductance bigind; power
        newpower;}; size 234sqft;};

    Into a Python list like this:
    ['clock','{','clockey','valley','}','object','house','{','name','myhouse',
        ';','object','ZIPload','{','inductance','bigind',';','power',
        'newpower','}','size','234sqft','}']
    """

    if file_path:
        with open(input_str, 'r') as glmFile:
            data = glmFile.read()

    else:
        data = input_str
    # Get rid of http for stylesheets because we don't need it and it conflicts
    # with comment syntax.
    data = re.sub(r'http:\/\/', '', data)
    # Strip comments.
    data = re.sub(r'\/\/.*(\s*)', '', data)
    # Also strip non-single whitespace because it's only for humans:
    data = data.replace('\r', '').replace('\t', ' ')
    # Tokenize around semicolons, braces and whitespace.
    tokenized = re.split(r'(;|\}|\{|\s)', data)
    # Get rid of whitespace strings.
    basic_list = [x for x in tokenized if x != '' and x != ' ']
    return basic_list


def _parse_token_list(token_list):
    """
    Given a list of tokens from a GLM, parse those into a tree data structure.

    """

    def current_leaf_add(key_f, value, tree_f, guid_stack_f):
        # Helper function to add to the current leaf we're visiting.
        current = tree_f
        for x in guid_stack_f:
            current = current[x]
        current[key_f] = value

    def list_to_string(list_in):
        # Helper function to turn a list of strings into one string with some
        # decent formatting.
        if len(list_in) == 0:
            return ''
        else:
            return reduce(lambda x, y: str(x) + ' ' + str(y), list_in[1:-1])

    # Tree variables.
    tree = {}
    guid = 0
    guid_stack = []

    # reverse the token list as pop() is way more efficient than pop(0)
    token_list = list(reversed(token_list))

    while token_list:
        # Pop, then keep going until we have a full token (i.e. 'object house',
        # not just 'object')
        full_token = []
        while full_token == [] or full_token[-1] not in ['{', ';', '}', '\n',
                                                         'shape']:
            full_token.append(token_list.pop())
        # Work with what we've collected.
        if full_token[0] == '#set':
            if full_token[-1] == ';':
                tree[guid] = {'omftype': full_token[0],
                              'argument': list_to_string(full_token)}
            else:
                tree[guid] = {'#set': list_to_string(full_token)}
            guid += 1
        elif full_token[0] == '#include':
            if full_token[-1] == ';':
                tree[guid] = {'omftype': full_token[0],
                              'argument': list_to_string(full_token)}
            else:
                tree[guid] = {'#include': list_to_string(full_token)}
            guid += 1
        elif full_token[0] == 'shape':
            while full_token[-1] not in ['\n']:
                full_token.append(token_list.pop())
            full_token[-2] = ''
            current_leaf_add(full_token[0], list_to_string(full_token[0:-1]),
                             tree, guid_stack)
            guid += 1
        elif full_token[-1] == '\n' or full_token[-1] == ';':
            # Special case when we have zero-attribute items (like #include,
            # #set, module).
            if guid_stack == [] and full_token != ['\n'] and \
                    full_token != [';']:

                tree[guid] = {'omftype': full_token[0],
                              'argument': list_to_string(full_token)}
                guid += 1
            # We process if it isn't the empty token (';')
            elif len(full_token) > 1:
                current_leaf_add(full_token[0], list_to_string(full_token),
                                 tree, guid_stack)
        elif full_token[-1] == '}':
            if len(full_token) > 1:
                current_leaf_add(full_token[0], list_to_string(full_token),
                                 tree, guid_stack)
            guid_stack.pop()
        elif full_token[0] == 'schedule':
            # Special code for those ugly schedule objects:
            if full_token[0] == 'schedule':
                while full_token[-1] not in ['}']:
                    full_token.append(token_list.pop())
                tree[guid] = {'object': 'schedule', 'name': full_token[1],
                              'cron': ' '.join(full_token[3:-2])}
                guid += 1
        elif full_token[-1] == '{':
            current_leaf_add(guid, {}, tree, guid_stack)
            guid_stack.append(guid)
            guid += 1
            # Wrapping this current_leaf_add is defensive coding so we don't
            # crash on malformed glm files.
            if len(full_token) > 1:
                # Do we have a clock/object or else an embedded configuration
                # object?
                if len(full_token) < 4:
                    current_leaf_add(full_token[0], full_token[-2], tree,
                                     guid_stack)
                else:
                    current_leaf_add('omfEmbeddedConfigObject',
                                     full_token[0] + ' ' +
                                     list_to_string(full_token), tree,
                                     guid_stack)

    # this section will catch old glm format and translate it. Not in the most
    # robust way but should work for now
    objects_to_delete = []
    for key in list(tree.keys()):
        if 'object' in list(tree[key].keys()):
            # if no name is present and the object name is the old syntax we
            # need to be creative and pull the object name and use it
            if 'name' not in list(tree[key].keys()) and \
                    tree[key]['object'].find(':') >= 0:
                tree[key]['name'] = tree[key]['object'].replace(':', '_')

            # strip the old syntax from the object name
            tree[key]['object'] = tree[key]['object'].split(':')[0]

            # for the remaining sytax we will replace ':' with '_'
            for line in tree[key]:
                tree[key][line] = tree[key][line].replace(':', '_')

            # deleting all recorders from the files
            if tree[key]['object'] == 'recorder' or \
                    tree[key]['object'] == 'group_recorder' or \
                    tree[key]['object'] == 'collector':
                objects_to_delete.append(key)

            # if we are working with fuses let's set the mean replace time to 1
            # hour if not specified. Then we aviod a warning!
            if tree[key][
                'object'] == 'fuse' and 'mean_replacement_time' not in list(
                    tree[key].keys()):

                tree[key]['mean_replacement_time'] = 3600.0

            # FNCS is not able to handle names that include "-" so we will
            # replace that with "_"
            if 'name' in list(tree[key].keys()):
                tree[key]['name'] = tree[key]['name'].replace('-', '_')
            if 'parent' in list(tree[key].keys()):
                tree[key]['parent'] = tree[key]['parent'].replace('-', '_')
            if 'from' in list(tree[key].keys()):
                tree[key]['from'] = tree[key]['from'].replace('-', '_')
            if 'to' in list(tree[key].keys()):
                tree[key]['to'] = tree[key]['to'].replace('-', '_')

    # deleting all recorders from the files
    for keys in objects_to_delete:
        del tree[keys]

    return tree


def sorted_write(in_tree):
    """
    Write out a GLM from a tree, and order all tree objects by their key.

    Sometimes Gridlab breaks if you rearrange a GLM.
    """

    sorted_keys = sorted(list(in_tree.keys()), key=int)
    output = ''
    try:
        for key in sorted_keys:
            output += _dict_to_string(in_tree[key]) + '\n'
    except ValueError:
        raise Exception
    return output


def _dict_to_string(in_dict):
    """
    Helper function: given a single dict representing a GLM object, concatenate
    it into a string.
    """

    # Handle the different types of dictionaries that are leafs of the tree
    # root:
    if 'omftype' in in_dict:
        return in_dict['omftype'] + ' ' + in_dict['argument'] + ';'
    elif 'module' in in_dict:
        return ('module ' + in_dict['module'] + ' {\n'
                + _gather_key_values(in_dict, 'module') + '}\n')
    elif 'clock' in in_dict:
        # return 'clock {\n' + gatherKeyValues(in_dict, 'clock') + '};\n'
        # This object has known property order issues writing it out explicitly
        clock_string = 'clock {\n'
        if 'timezone' in in_dict:
            clock_string = clock_string + '\ttimezone ' + in_dict[
                'timezone'] + ';\n'
        if 'starttime' in in_dict:
            clock_string = clock_string + '\tstarttime ' + in_dict[
                'starttime'] + ';\n'
        if 'stoptime' in in_dict:
            clock_string = clock_string + '\tstoptime ' + in_dict[
                'stoptime'] + ';\n'
        clock_string = clock_string + '}\n'
        return clock_string
    elif 'object' in in_dict and in_dict['object'] == 'schedule':
        return 'schedule ' + in_dict['name'] + ' {\n' + in_dict[
            'cron'] + '\n};\n'
    elif 'object' in in_dict:
        return ('object ' + in_dict['object'] + ' {\n'
                + _gather_key_values(in_dict, 'object') + '};\n')
    elif 'omfEmbeddedConfigObject' in in_dict:
        return in_dict['omfEmbeddedConfigObject'] + ' {\n' + \
               _gather_key_values(in_dict, 'omfEmbeddedConfigObject') + '};\n'
    elif '#include' in in_dict:
        return '#include ' + in_dict['#include']
    elif '#define' in in_dict:
        return '#define ' + in_dict['#define'] + '\n'
    elif '#set' in in_dict:
        return '#set ' + in_dict['#set']
    elif 'class' in in_dict:
        prop = ''
        # this section will ensure we can get around the fact that you can't
        # have to key's with the same name!
        if 'variable_types' in list(
                in_dict.keys()) and 'variable_names' in list(
                in_dict.keys()) and len(in_dict['variable_types']) == len(
                in_dict['variable_names']):

            prop += 'class ' + in_dict['class'] + ' {\n'
            for x in range(len(in_dict['variable_types'])):
                prop += '\t' + in_dict['variable_types'][x] + ' ' + \
                        in_dict['variable_names'][x] + ';\n'

            prop += '}\n'
        else:
            prop += 'class ' + in_dict['class'] + ' {\n' + _gather_key_values(
                in_dict, 'class') + '}\n'

        return prop


def _gather_key_values(in_dict, key_to_avoid):
    """
    Helper function: put key/value pairs for objects into the format GLD needs.
    """

    other_key_values = ''
    for key in in_dict:
        if type(key) is int:
            # WARNING: RECURSION HERE
            other_key_values += _dict_to_string(in_dict[key])
        elif key != key_to_avoid:
            if key == 'comment':
                other_key_values += (in_dict[key] + '\n')
            elif key == 'name' or key == 'parent':
                if len(in_dict[key]) <= 62:
                    other_key_values += (
                            '\t' + key + ' ' + str(in_dict[key]) + ';\n')
                else:
                    warnings.warn(
                        ("{:s} argument is longer that 64 characters. "
                         + " Truncating {:s}.").format(key, in_dict[key]),
                        RuntimeWarning)
                    other_key_values += ('\t' + key + ' '
                                         + str(in_dict[key])[0:62]
                                         + '; // truncated from {:s}\n'.format(
                                            in_dict[key]))
            else:
                other_key_values += ('\t' + key + ' ' + str(in_dict[key])
                                     + ';\n')
    return other_key_values


class GLMManager:
    """Class to manage a GridLAB-D model (.glm).

    Primary capabilities:
        - Add item to model
        - Modify item in model
        - TODO: remove item from model
        - TODO: remove properties from items

    """

    def __init__(self, model, model_is_path=True):
        """Initialize by parsing given model.

        :param model: Path to or string of GridLAB-D model.
        :type model: str
        :param model_is_path: Specifies if model is path (True) or
               string of model (False)
        :type model_is_path: Boolean
        """

        # Parse the model.
        self.model_dict = parse(model, model_is_path)

        # The model dict has increasing integer keys so the model can
        # later be written in order (since GridLAB-D cares sometimes).
        # Get the first and last keys.
        keys = list(self.model_dict.keys())
        # Set keys for adding items to beginning or end of model.
        self.append_key = max(keys) + 1
        self.prepend_key = min(keys) - 1

        # Define items we won't include in the model_map.
        self.no_map = ('set', 'include')
        # Define non-object items.
        self.non_objects = ('clock', 'module', 'include', 'set', 'omftype')

        # Initialize model_map.
        self.model_map = {'clock': [], 'module': {}, 'object': {},
                          'object_unnamed': []}
        # Map objects in the model.
        self._map_model_dict()

    def _update_append_key(self):
        """Add one to the append_key."""
        self.append_key += 1

    def _update_prepend_key(self):
        """Subtract one from the prepend_key."""
        self.prepend_key -= 1

    def _map_model_dict(self):
        """Generate mapping of model_dict by object type.

        Dictionary hierarchy will be as follows:
        <object type>
            <object name>
                <object properties>

        NOTE: each item will be stored as [model_key, item_dict] in the
            map.

        :returns: map_dict
        """

        # Loop over the model_dict.
        for model_key, item_dict in self.model_dict.items():

            # Get the item type.
            item_type = self._get_item_type(item_dict)

            # If it's an object, use the object function.
            if item_type == 'object':
                self._add_object_to_map(model_key, item_dict)

            elif item_type == 'clock':
                self._add_clock_to_map(model_key, item_dict)

            elif item_type == 'module':
                # Map by module name.
                self._add_module_to_map(model_key, item_dict)

            elif item_type == 'omftype':
                # Map (only if it's a module)
                if item_dict['omftype'] == 'module':
                    self._add_module_to_map(model_key, item_dict)

            elif item_type in self.no_map:
                # No mapping for now.
                pass

            else:
                # Unexpected type, raise warning.
                raise UserWarning('Unimplemented item: {}'.format(item_dict))

        # That's it. Easy, isn't it?

    def _add_clock_to_map(self, model_key, clock_dict):
        """Add clock to the model map.

        :param model_key: key to model_dict
        :param clock_dict: dictionary representing clock.
        :type clock_dict: dict
        """
        # Only allow one clock.
        if len(self.model_map['clock']) > 0:
            raise UserWarning('Multiple clocks defined!')

        # Map it.
        self.model_map['clock'] = [model_key, clock_dict]

    def _add_module_to_map(self, model_key, module_dict):
        """Add module to the model map by module name.

        :param model_key: key to model_dict
        :param module_dict: dictionary defining module.
        :type module_dict: dict
        """

        # Get the module name from the dict.
        if 'module' in module_dict:
            module_name = module_dict['module']
        elif 'omftype' in module_dict:
            module_name = module_dict['argument']
        else:
            # Bad dict.
            raise UserWarning('Malformed module_dict: {}'.format(module_dict))

        # Ensure we aren't over-writing existing module.
        if module_name in self.model_map['module']:
            s = 'Module {} is already present!'.format(module_name)
            raise UserWarning(s)

        # Map it by name.
        self.model_map['module'][module_name] = [model_key, module_dict]

    def _add_object_to_map(self, model_key, object_dict):
        """Add object to the model_map.

        :param: object_dict: Dictionary of all object attributes.
        :type: object_dict: dict
        """
        # Grab reference to the object sub-dict.
        object_map = self.model_map['object']

        # Get type of object.
        obj_type = object_dict['object']

        # Define key object pair
        key_obj = [model_key, object_dict]

        # If this type isn't in the map, add it. NOTE: this can lead to
        # empty entries if the object isn't named.
        if obj_type not in object_map:
            object_map[obj_type] = {}

        try:
            # Never try to map an already existing named object.
            if object_dict['name'] in object_map[obj_type]:
                s = '{} already exists in the {} map!'
                raise UserWarning(s.format(object_dict['name'], obj_type))

        except KeyError:
            # Unnamed object. Add it to the unnamed list.
            self.model_map['object_unnamed'].append(key_obj)

        else:
            # Named object, map it.
            object_map[obj_type][object_dict['name']] = key_obj

        # No need to return; we're directly updating self.model_map

    def write_model(self, out_path):
        """Helper to write out the model_dict.

        :param out_path: Full path to write model out to.
        :type out_path: str
        """

        # Get dictionary as a string.
        model_string = sorted_write(self.model_dict)

        # Write it.
        with open(out_path, 'w') as f:
            f.write(model_string)

    def add_item(self, item_dict):
        """Add and map a new item.

        :param item_dict:
        :type item_dict: dict
        """
        # Get type of item.
        item_type = self._get_item_type(item_dict)

        # Ensure all fields are strings, cast values to strings.
        for k in item_dict:
            # Check key.
            if not isinstance(k, str):
                raise UserWarning('All keys must be strings!')

            # Make sure value is string.
            item_dict[k] = str(item_dict[k])

        if item_type == 'object':
            # Use _add_object method to map and add the object.
            self._add_object(item_dict)
        elif item_type in self.non_objects:
            # Use _add_non_object method to map and add the item.
            self._add_non_object(item_type, item_dict)
        else:
            s = 'No add method for item type {}'.format(item_type)
            raise UserWarning(s)

    def _add_object(self, object_dict):
        """Add and map object.

        :param object_dict:
        :type object_dict: dict
        """
        # Attempt to map the object first. This will raise a UserWarning
        # if a named object of the same type already exists.
        self._add_object_to_map(self.append_key, object_dict)

        # Add the object to the end of the model.
        # TODO: which objects need added to the beginning?
        self.model_dict[self.append_key] = object_dict

        # Update append key.
        self._update_append_key()

    def _find_object(self, obj_type, obj_name):
        """Find object by name in the model_map, if it exists.

        :param: obj_type: type of the object to look up.
        :type: obj_type: str
        :param: obj_name: name of the object to look up.
        :type: obj_name: str
        """
        try:
            # Simply look it up by type and name.
            obj = self.model_map['object'][obj_type][obj_name][1]
        except KeyError:
            # No dice. This object doesn't exist in the model.
            obj = None

        return obj

    def _add_non_object(self, item_type, item_dict):
        """Add a non-object to the model.

        non-objects are listed in self.non_objects.

        :param item_type: type of object to be added.
        :type item_type: str
        :param item_dict: dictionary with object properties
        :type item_dict: dict
        """

        # Map item.
        if item_type == 'clock':
            # Map clock.
            self._add_clock_to_map(self.prepend_key, item_dict)

        elif item_type == 'module':
            # Map module.
            self._add_module_to_map(self.prepend_key, item_dict)

        elif item_type in self.no_map:
            # No mapping.
            pass

        else:
            s = 'No add method for {} item type.'.format(item_type)
            raise UserWarning(s)

        # Add to beginning of model.
        self.model_dict[self.prepend_key] = item_dict

        # Update prepend key.
        self._update_prepend_key()

    def modify_item(self, item_dict):
        """Modify an item in the model.

        NOTE: this method CANNOT be used to change an object's name.

        :param item_dict
        """
        # Get type.
        item_type = self._get_item_type(item_dict)

        if item_type == 'object':
            if 'name' not in item_dict:
                raise UserWarning('To update an object, its name is needed.')
            # Look up object. Raises UserWarning if not found.
            obj = self._lookup_object(object_type=item_dict.pop('object'),
                                      object_name=item_dict.pop('name'))

            # Successfully grabbed object. Update it.
            obj = self._modify_item(obj, item_dict)

        elif item_type == 'clock':
            # No need to modify clock definition.
            item_dict.pop('clock')

            # Get clock.
            clock = self._lookup_clock()

            # Update the clock.
            clock = self._modify_item(clock, item_dict)

        elif item_type == 'module':
            # Get module
            module = self._lookup_module(module_name=item_dict.pop('module'))

            # Modify it. Simple if it isn't an 'omftype' style module.
            if 'omftype' in module:
                # We need to change up this dictionary.
                module['module'] = module['argument']
                module.pop('omftype')
                module.pop('argument')

            # Modify it.
            module = self._modify_item(module, item_dict)

        else:
            s = 'Cannot modify item of type {}'.format(item_type)
            raise UserWarning(s)

    @staticmethod
    def _modify_item(item, update_dict):
        """Simple helper to update an existing item.

        NOTE: We're casting everything to strings, so if the 'str()'
            method fails, this method fails :)

        Note that only properties from update_dict will be modified (or
            added)
        """
        for k in update_dict:
            item[k] = str(update_dict[k])

        return item

    def remove_properties_from_item(self, item_dict, property_list):
        """Remove properties from an item."""

        # Get type.
        item_type = self._get_item_type(item_dict)

        if item_type == 'object':
            # Check for name.
            if 'name' not in item_dict:
                raise UserWarning('To update an object, its name is needed.')

            # Get object. Raises UserWarning if not found.
            obj = self._lookup_object(object_type=item_dict['object'],
                                      object_name=item_dict['name'])

            # Remove properties.
            self._remove_from_item(obj, property_list)

        elif item_type == 'clock':
            # Get clock.
            clock = self._lookup_clock()

            # Remove properties.
            clock = self._remove_from_item(clock, property_list)

        elif item_type == 'module':
            # Get module.
            module = self._lookup_module(module_name=item_dict['module'])

            module = self._remove_from_item(module, property_list)

        else:
            s = 'Cannot remove properties from items of type {}'.format(
                item_type)
            raise UserWarning(s)

    def remove_item(self, item_dict):
        """Remove item from both the model_dict and model_map.

        :param item_dict: dictionary defining object to remove.
        """
        # Get type
        item_type = self._get_item_type(item_dict)

        if item_type == 'object':
            # Check for name (not currently supporting removal of
            # unnamed objects)
            try:
                obj_name = item_dict['name']
            except KeyError:
                s = 'Cannot remove unnamed objects!'
                raise UserWarning(s)

            # Remove from model.
            obj_type = item_dict['object']
            self.model_dict.pop(self.model_map['object'][obj_type][
                                    obj_name][0])

            # Remove from the map.
            self.model_map['object'][obj_type].pop(obj_name)

        elif item_type == 'clock':
            # Ensure there's a clock to remove.
            self._lookup_clock()

            # Remove from model.
            self.model_dict.pop(self.model_map['clock'][0])

            # Remove from the map by resetting clock to empty list.
            self.model_map['clock'] = []

        elif item_type == 'module':
            # Ensure there's a module to remove.
            module_name = item_dict['module']
            self._lookup_module(module_name)

            # Remove from model.
            self.model_dict.pop(self.model_map['module'][module_name][0])

            # Remove from the map.
            self.model_map['module'].pop(module_name)
        else:
            s = 'Cannot remove item of type {}'.format(item_type)
            raise UserWarning(s)

    def _lookup_object(self, object_type, object_name):
        # Simply look it up and update it.
        try:
            obj = self.model_map['object'][object_type][object_name][1]
        except KeyError:
            s = ('Object of type {} and name {} does not exist in the '
                 + 'model map!').format(object_type, object_name)
            raise UserWarning(s)
        else:
            return obj

    def _lookup_module(self, module_name):
        # Ensure named module is present.
        try:
            module = self.model_map['module'][module_name][1]
        except KeyError:
            s = 'Module {} does not exist!'.format(module_name)
            raise UserWarning(s)
        else:
            return module

    @staticmethod
    def _remove_from_item(item, remove_list):
        """Simple helper to remove fields from an item."""
        for k in remove_list:
            # Will raise KeyError if asked to remove non-existent item
            try:
                item.pop(k)
            except KeyError:
                s = 'Could not remove nonexistent field {}'.format(k)
                raise UserWarning(s)

        return item

    @staticmethod
    def _get_item_type(item_dict):
        """Determine type of given item."""

        if 'object' in item_dict:
            item_type = 'object'
        elif 'module' in item_dict:
            item_type = 'module'
        elif 'clock' in item_dict:
            item_type = 'clock'
        elif '#include' in item_dict:
            item_type = 'include'
        elif '#set' in item_dict:
            item_type = 'set'
        elif 'omftype' in item_dict:
            item_type = 'omftype'
        else:
            raise UserWarning('Unknown type! Item: {}'.format(item_dict))

        return item_type

    def _lookup_clock(self):
        try:
            clock = self.model_map['clock'][1]
        except IndexError:
            raise UserWarning('Clock does not exist!')
        else:
            return clock

def _test():
    import time
    start = time.time()
    model_manager = GLMManager('R2_12_47_2_AMI_5_min.glm')

    # Print first and last 20.
    for i in range(20):
        print(model_manager.model_dict[i])

    for i in range(model_manager.append_key - 1, model_manager.append_key -
                                                 21, -1):
        print(model_manager.model_dict[i])

    model_manager.write_model('R2_out.glm')
    '''
    # cProfile.run('re.compile("foo|bar")')
    # Location in docker container
    feeder_location = 'ieee8500_base.glm'
    feeder_dictionary = parse(feeder_location)
    # Map the model.
    model_map = map_dict(in_dict=feeder_dictionary)
    # print(feeder_dictionary)
    feeder_str = sorted_write(feeder_dictionary)
    glm_file = open('ieee8500_base_out.glm', 'w')
    glm_file.write(feeder_str)
    glm_file.close()
    '''
    end = time.time()
    print('successfully completed in {:0.1f} seconds'.format(end - start))


if __name__ == '__main__':
    _test()