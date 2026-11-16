"""Merging non-destructif des référentiels XML du simulateur Houston.
Ne remplace JAMAIS les entrées existantes ; insertion textuelle localisée.
"""
from __future__ import annotations
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime
import xml.etree.ElementTree as ET

BASIC_TAG = 'basic_signal_type'
COMP_TAG = 'composite_signal_type'

@dataclass(frozen=True)
class Proposal:
    name: str
    category: str  # basic / composite
    source: str
    add_layers: bool
    add_data: bool
    layer_id: str
    warning: str = ''


def xml_root(path):
    # Expat n'expanse pas les entités externes. Aucun réseau pour les fichiers source.
    return ET.parse(path).getroot()


def nodes_from_source(root):
    if root.tag == 'feature_type':
        return [root]
    if root.tag in (BASIC_TAG, COMP_TAG):
        return [root]
    return [e for e in root.iter() if e.tag in ('feature_type', BASIC_TAG, COMP_TAG)]


def classify(node):
    name = (node.get('name') if node.tag == 'feature_type' else node.get('feature_type_name')) or ''
    name = name.strip()
    if not name:
        return None
    if node.tag == COMP_TAG or name.startswith('CompositeSignal_'):
        return name, 'composite', '320'
    if node.tag == BASIC_TAG or name.startswith('Signal_'):
        # Signaux lumineux dans layer 352; panneaux voieside dans 351
        group = (node.get('group') or '').lower()
        family = ' '.join((v.get('name') or '') for v in node.findall('.//family')).lower()
        if name.startswith('Signal_US_WS_') or 'wayside' in family or 'signs' in group:
            return name, 'basic', '351'
        return name, 'basic', '352'
    # Ignore explicitement les autres feature-types (balises, poles, etc.)
    return None


def existing_names(root, tag, attr):
    return {e.get(attr) for e in root.iter(tag) if e.get(attr)}


def find_layer(root, layer_id):
    for e in root.iter('layer'):
        if e.get('id') == layer_id:
            return e
    raise ValueError(f'Layer id={layer_id} absent de layers.xml')


def make_basic_xml(name, node):
    if node.tag == BASIC_TAG:
        # Une définition OKRP explicite peut contenir des règles fonctionnelles :
        # conserver son contenu complet plutôt que reconstruire un type générique.
        return '\t\t\t' + ET.tostring(node, encoding='unicode').strip()
    # On reproduit la structure du type statique des signaux OKRP existants.
    # Si la source expose des états compatibles, on les réutilise; on n'invente pas de
    # correspondance pour un état Visible absent de la bibliothèque.
    dynamic = node.find('feature_type_state_type')
    src_states = [x.get('name') for x in dynamic.findall('feature_type_state') if x.get('name')] if dynamic is not None else []
    # Les états visibles d'un panneau statique ne sont pas des états d'aspects OKRP.
    if src_states == ['Visible']:
        src_states = []
    states = '<states />' if not src_states else '<states>\n' + '\n'.join(f'\t\t\t\t\t<state name="{escape_attr(s)}" />' for s in src_states) + '\n\t\t\t\t</states>'
    # Les paramètres / états de l'objet 3D ne doivent pas être copiés vers la bibliothèque OKRP.
    modify = 'true' if 'Speed' in name or 'SchoolZone' in name else 'false'
    return (f'\t\t\t<basic_signal_type feature_type_name="{escape_attr(name)}" is_sc_signal="false" semantic="">\n'
            f'\t\t\t\t{states}\n'
            f'\t\t\t\t<modify_text modify="{modify}"><default_text /></modify_text>\n'
            f'\t\t\t\t<behaviour>\n'
            f'\t\t\t\t\t<filter value="0" />\n'
            f'\t\t\t\t\t<section_busiers_states />\n'
            f'\t\t\t\t\t<sequencable_states />\n'
            f'\t\t\t\t\t<init><preferred_states /><avoid_states /></init>\n'
            f'\t\t\t\t\t<rules><default_states /></rules>\n'
            f'\t\t\t\t</behaviour>\n'
            f'\t\t\t</basic_signal_type>')


def escape_attr(value):
    return (value.replace('&', '&amp;').replace('"', '&quot;').replace('<', '&lt;'))


def make_composite_xml(name):
    return f'\t\t\t<composite_signal_type feature_type_name="{escape_attr(name)}" />'


def make_layer_xml(name, layer_id):
    return f'\t\t\t\t<feature_type_layer feature_type="{escape_attr(name)}" display_name="{escape_attr(name)}" />'


def insert_before_closing(text, end_tag, fragment, indent):
    """Insère juste avant une balise fermante sur sa ligne, sans reformater le XML."""
    expression = re.compile(r'(?m)^([ \t]*)' + re.escape(end_tag) + r'[ \t]*\r?$')
    matches = list(expression.finditer(text))
    if len(matches) != 1:
        raise ValueError(f'Balise de fermeture ambiguë ou introuvable: {end_tag} ({len(matches)})')
    match = matches[0]
    if match.group(1) != indent:
        raise ValueError(f'Indentation inattendue de {end_tag}')
    newline = '\r\n' if '\r\n' in text else '\n'
    return text[:match.start()] + fragment.replace('\n', newline) + newline + text[match.start():]


def add_in_section(text, parent_tag, xml_fragments):
    if not xml_fragments:
        return text
    # Cible le dernier </parent_tag> ; ces sections n'existent qu'une seule fois.
    close = f'</{parent_tag}>'
    indent = '\t\t' if parent_tag in ('basic_signal_types', 'composite_signal_types') else '\t\t\t'
    return insert_before_closing(text, close, ('\n'.join(xml_fragments)), indent)


def add_to_layer(text, layer_id, xml_fragments):
    if not xml_fragments:
        return text
    match = re.search(r'(?m)^\s*<layer\s+id="' + re.escape(layer_id) + r'"[^>]*>', text)
    if not match:
        raise ValueError(f'Impossible de trouver la layer {layer_id}')
    # Parcours des balises layer ouvrantes/fermantes pour trouver sa fermeture.
    token_re = re.compile(r'<layer\b[^>]*?/?>|</layer\s*>')
    depth = 0
    for t in token_re.finditer(text, match.start()):
        s = t.group(0)
        if s.startswith('</'):
            depth -= 1
            if depth == 0:
                line_start = text.rfind('\n', 0, t.start()) + 1
                indent = text[line_start:t.start()]
                if indent.strip():
                    raise ValueError('Fermeture de layer inattendue')
                newline = '\r\n' if '\r\n' in text else '\n'
                return text[:line_start] + newline.join(xml_fragments) + newline + text[line_start:]
        elif not s.endswith('/>'):
            depth += 1
    raise ValueError(f'Fermeture du layer {layer_id} introuvable')


class Merger:
    def __init__(self, folder, layers_path, data_path):
        self.folder = Path(folder).resolve()
        self.layers_path = Path(layers_path).resolve()
        self.data_path = Path(data_path).resolve()
        self.entries = {}
        self.proposals = []
        self.notes = []

    def scan(self):
        if not self.folder.is_dir():
            raise ValueError('Dossier source introuvable')
        if self.layers_path == self.data_path:
            raise ValueError('Les deux fichiers cibles doivent être distincts')
        layers_root = xml_root(self.layers_path)
        data_root = xml_root(self.data_path)
        if layers_root.tag != 'config' or data_root.tag != 'okrp_data':
            raise ValueError('Fichiers cibles incorrects: attendu <config> et <okrp_data>')
        library = data_root.find('signals_library')
        if library is None or library.find('basic_signal_types') is None or library.find('composite_signal_types') is None:
            raise ValueError('Structure signals_library absente ou incomplète')
        for layer_id in ('320','351','352'):
            find_layer(layers_root, layer_id)
        existing_layer = existing_names(layers_root, 'feature_type_layer', 'feature_type')
        existing_basic = existing_names(library, BASIC_TAG, 'feature_type_name')
        existing_composite = existing_names(library, COMP_TAG, 'feature_type_name')
        self.entries, self.proposals, self.notes = {}, [], []
        for file in sorted(self.folder.rglob('*.xml')):
            if file.resolve() in (self.layers_path, self.data_path):
                continue
            try:
                root = xml_root(file)
                for node in nodes_from_source(root):
                    info = classify(node)
                    if info is None:
                        continue
                    name, category, layer_id = info
                    if name in self.entries:
                        previous = self.entries[name][2]
                        self.notes.append(f'Doublon source ignoré : {name} ({file.name}; premier : {previous.name})')
                        continue
                    self.entries[name] = (node, category, file, layer_id)
                    is_in_data = name in (existing_basic if category == 'basic' else existing_composite)
                    conflicting = name in (existing_composite if category == 'basic' else existing_basic)
                    warning = 'Conflit catégorie : même nom déjà utilisé ailleurs dans OKRP' if conflicting else ''
                    self.proposals.append(Proposal(name, category, str(file), name not in existing_layer and not conflicting, not is_in_data and not conflicting, layer_id, warning))
            except ET.ParseError as err:
                self.notes.append(f'XML invalide ignoré: {file}: {err}')
            except OSError as err:
                self.notes.append(f'Erreur lecture ignorée: {file}: {err}')
        return self.proposals

    def build(self, selected_names=None):
        if not self.entries:
            return self.layers_path.read_bytes(), self.data_path.read_bytes(), []
        selected = set(selected_names) if selected_names is not None else {p.name for p in self.proposals}
        chosen = [p for p in self.proposals if p.name in selected and not p.warning]
        data_fragments = {'basic': [], 'composite': []}
        layers_fragments = {'320': [], '351': [], '352': []}
        for p in chosen:
            node = self.entries[p.name][0]
            if p.add_data:
                data_fragments[p.category].append(make_basic_xml(p.name, node) if p.category == 'basic' else make_composite_xml(p.name))
            if p.add_layers:
                layers_fragments[p.layer_id].append(make_layer_xml(p.name, p.layer_id))
        # Décodage conserve l'encodage source (UTF8 / UTF8-SIG). Les XML fournis sont UTF-8.
        a_raw, b_raw = self.layers_path.read_bytes(), self.data_path.read_bytes()
        for path, raw in ((self.layers_path, a_raw), (self.data_path,b_raw)):
            prefix = raw[:200].decode('ascii', 'ignore')
            if re.search(r'encoding=[\'\"]([^\'\"]+)', prefix) and not re.search(r'encoding=[\'\"]utf-8[\'\"]', prefix, re.I):
                raise ValueError(f'Encodage non UTF-8 non pris en charge sans conversion: {path}')
        a, b = a_raw.decode('utf-8-sig'), b_raw.decode('utf-8-sig')
        for k in ('320', '351', '352'):
            a = add_to_layer(a, k, layers_fragments[k])
        for category, tag in (('basic', 'basic_signal_types'), ('composite', 'composite_signal_types')):
            b = add_in_section(b, tag, data_fragments[category])
        bom_a = b'\xef\xbb\xbf' if a_raw.startswith(b'\xef\xbb\xbf') else b''
        bom_b = b'\xef\xbb\xbf' if b_raw.startswith(b'\xef\xbb\xbf') else b''
        out_a, out_b = bom_a + a.encode('utf-8'), bom_b + b.encode('utf-8')
        # Relecture: assure XML bien formé, et aucune suppression de feature_types existants.
        new_la = ET.fromstring(out_a)
        new_da = ET.fromstring(out_b)
        old_la = ET.fromstring(a_raw)
        old_da = ET.fromstring(b_raw)
        for tag, attr, old_root, new_root in (
            ('feature_type_layer','feature_type', old_la,new_la),
            (BASIC_TAG,'feature_type_name',old_da,new_da),
            (COMP_TAG,'feature_type_name',old_da,new_da)):
            old_list = [x.get(attr) for x in old_root.iter(tag)]
            new_list = [x.get(attr) for x in new_root.iter(tag)]
            if new_list[:len(old_list)] != old_list:
                # Un ajout au layer 320 peut être avant l'ancien layer 351: comparaison par sous-séquences.
                it = iter(new_list)
                if not all(any(v == old for v in it) for old in old_list):
                    raise ValueError('Validation échouée: des entrées existantes ont été modifiées')
        changed = [p for p in chosen if p.add_layers or p.add_data]
        return out_a, out_b, changed

    def apply(self, selected_names=None):
        new_layers, new_data, changes = self.build(selected_names)
        old_layers, old_data = self.layers_path.read_bytes(), self.data_path.read_bytes()
        if new_layers == old_layers and new_data == old_data:
            return [], []
        stamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        backup_paths = []
        for target in (self.layers_path, self.data_path):
            backup = target.with_name(target.name + f'.backup_{stamp}')
            shutil.copy2(target, backup)
            backup_paths.append(backup)
        # Préparer fichiers temporaires sur le même disque, remplacer après validation.
        temps = []
        try:
            for target, data in ((self.layers_path, new_layers), (self.data_path, new_data)):
                fd, temp = tempfile.mkstemp(prefix=f'.{target.name}.', dir=target.parent)
                temps.append(temp)
                with os.fdopen(fd, 'wb') as f:
                    f.write(data)
                    f.flush()
                    os.fsync(f.fileno())
                shutil.copymode(target, temp)
            try:
                os.replace(temps[0], self.layers_path)
                os.replace(temps[1], self.data_path)
            except Exception:
                # Restoration des deux originaux depuis leurs sauvegardes.
                shutil.copy2(backup_paths[0], self.layers_path)
                shutil.copy2(backup_paths[1], self.data_path)
                raise
        finally:
            for temp in temps:
                if os.path.exists(temp):
                    os.unlink(temp)
        return changes, backup_paths
