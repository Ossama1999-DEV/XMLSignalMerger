"""Interface Tkinter — Houston XML Signal Merger. Python 3.9+ uniquement."""
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from merger import Merger

class Application(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Houston — XML Signal Merger')
        self.geometry('1120x740')
        self.minsize(860, 560)
        self.folder = tk.StringVar()
        self.layers = tk.StringVar()
        self.data = tk.StringVar()
        self.status = tk.StringVar(value='Sélectionne le dossier source et les deux référentiels XML.')
        self.merger = None
        self.item_to_name = {}
        self._create_ui()

    def _create_ui(self):
        style = ttk.Style(self)
        if 'clam' in style.theme_names():
            style.theme_use('clam')
        style.configure('Heading.TLabel', font=('Arial', 15, 'bold'))
        panel = ttk.Frame(self, padding=14)
        panel.pack(fill='both', expand=True)
        ttk.Label(panel, text='XML Signal Merger — Houston LRV', style='Heading.TLabel').pack(anchor='w', pady=(0, 8))
        ttk.Label(panel, text='Compare les feature types d’un dossier XML, ajoute uniquement les références absentes et sauvegarde les originaux.').pack(anchor='w', pady=(0, 15))
        for label, variable, isfolder in (
            ('Dossier des nouveaux XML :', self.folder, True),
            ('layers.xml :', self.layers, False),
            ('signals_okrp_data.xml :', self.data, False)):
            row = ttk.Frame(panel)
            row.pack(fill='x', pady=4)
            ttk.Label(row, text=label, width=29).pack(side='left')
            ttk.Entry(row, textvariable=variable).pack(side='left', fill='x', expand=True, padx=6)
            ttk.Button(row, text='Parcourir…', command=lambda v=variable, f=isfolder: self.choose(v, f), width=14).pack(side='right')
        tools = ttk.Frame(panel)
        tools.pack(fill='x', pady=(17, 8))
        ttk.Button(tools, text='1. Analyser les XML', command=self.analyze).pack(side='left', padx=(0, 8))
        ttk.Button(tools, text='Tout sélectionner', command=self.select_all).pack(side='left', padx=(0, 8))
        ttk.Button(tools, text='Tout désélectionner', command=self.select_none).pack(side='left', padx=(0, 8))
        ttk.Button(tools, text='2. Appliquer et sauvegarder', command=self.apply).pack(side='right')
        ttk.Label(panel, text='Clique sur une ligne pour sélectionner/désélectionner. Vert = ajout, gris = déjà présent, orange = conflit.').pack(anchor='w', pady=(0, 7))
        columns = ('select', 'name', 'type', 'layer', 'in_layers', 'in_data', 'file')
        tree_frame = ttk.Frame(panel)
        tree_frame.pack(fill='both', expand=True)
        self.tree = ttk.Treeview(tree_frame, columns=columns, show='headings', selectmode='browse')
        labels = {'select':'Choix','name':'Feature type','type':'Catégorie','layer':'Layer','in_layers':'layers.xml','in_data':'OKRP','file':'Fichier source'}
        widths = {'select':55,'name':370,'type':95,'layer':56,'in_layers':104,'in_data':104,'file':230}
        for c in columns:
            self.tree.heading(c, text=labels[c])
            self.tree.column(c, width=widths[c], anchor=('center' if c in ('select','type','layer','in_layers','in_data') else 'w'), stretch=c in ('name','file'))
        vs = ttk.Scrollbar(tree_frame, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=vs.set)
        self.tree.pack(side='left', fill='both', expand=True)
        vs.pack(side='right', fill='y')
        self.tree.tag_configure('add', foreground='#087c32')
        self.tree.tag_configure('present', foreground='#666666')
        self.tree.tag_configure('problem', foreground='#b86c00')
        self.tree.bind('<ButtonRelease-1>', self.toggle)
        ttk.Label(panel, textvariable=self.status).pack(anchor='w', pady=(10, 4))
        ttk.Label(panel, text='Rapport :', font=('Arial', 10, 'bold')).pack(anchor='w')
        self.log = tk.Text(panel, height=7, wrap='word', state='disabled')
        self.log.pack(fill='x', pady=(2, 0))

    def choose(self, variable, folder):
        value = filedialog.askdirectory(title='Dossier des XML') if folder else filedialog.askopenfilename(title='Sélectionne le fichier XML', filetypes=[('Fichiers XML', '*.xml'),('Tous', '*.*')])
        if value:
            variable.set(value)

    def write(self, content):
        self.log.configure(state='normal')
        self.log.insert('end', content + '\n')
        self.log.see('end')
        self.log.configure(state='disabled')

    def analyze(self):
        if not all((self.folder.get(), self.layers.get(), self.data.get())):
            messagebox.showwarning('Fichiers manquants', 'Sélectionne les trois chemins.')
            return
        try:
            self.merger = Merger(self.folder.get(), self.layers.get(), self.data.get())
            proposals = self.merger.scan()
        except Exception as exc:
            messagebox.showerror('Erreur analyse', str(exc))
            self.merger = None
            return
        self.tree.delete(*self.tree.get_children())
        self.item_to_name = {}
        missing = 0
        for idx, p in enumerate(proposals):
            editable = p.add_layers or p.add_data
            missing += bool(editable)
            mark = '☑' if editable and not p.warning else '☐'
            tag = 'problem' if p.warning else ('add' if editable else 'present')
            values = (mark, p.name, p.category, p.layer_id,
                      'À ajouter' if p.add_layers else 'Présent',
                      'À ajouter' if p.add_data else 'Présent', Path(p.source).name)
            item = self.tree.insert('', 'end', iid=str(idx), values=values, tags=(tag,))
            self.item_to_name[item] = p.name
        self.status.set(f'{len(proposals)} types détectés — {missing} à compléter — {len(self.merger.notes)} avertissement(s)')
        self.write(f'Analyse : {len(proposals)} types XML, {missing} nécessitent un ajout.')
        for note in self.merger.notes:
            self.write('⚠ ' + note)

    def toggle(self, event):
        item = self.tree.identify_row(event.y)
        if not item:
            return
        values = list(self.tree.item(item, 'values'))
        if values[4] == 'Présent' and values[5] == 'Présent':
            return
        if self.tree.item(item, 'tags')[0] == 'problem':
            return
        values[0] = '☐' if values[0] == '☑' else '☑'
        self.tree.item(item, values=values)

    def select_all(self):
        for item in self.tree.get_children():
            values = list(self.tree.item(item, 'values'))
            if (values[4] == 'À ajouter' or values[5] == 'À ajouter') and self.tree.item(item, 'tags')[0] != 'problem':
                values[0] = '☑'
                self.tree.item(item, values=values)

    def select_none(self):
        for item in self.tree.get_children():
            values = list(self.tree.item(item, 'values'))
            values[0] = '☐'
            self.tree.item(item, values=values)

    def apply(self):
        if self.merger is None:
            messagebox.showwarning('Analyse requise', 'Commence par analyser les XML.')
            return
        selected = [self.item_to_name[i] for i in self.tree.get_children() if self.tree.item(i, 'values')[0] == '☑']
        if not selected:
            messagebox.showinfo('Aucun ajout', 'Aucune ligne sélectionnée.')
            return
        if not messagebox.askyesno('Confirmer les modifications',
                f'Ajouter les références manquantes de {len(selected)} type(s) ?\n\n'
                'Les fichiers layers.xml et signals_okrp_data.xml seront modifiés directement.\n'
                'Une sauvegarde horodatée de CHACUN sera créée avant toute modification.'):
            return
        try:
            # Refaire une analyse juste avant écriture: protège contre les éditions externes.
            self.merger.scan()
            changes, backups = self.merger.apply(selected)
            self.write(f'Ajouts effectués : {len(changes)}')
            for p in changes:
                self.write(f' + {p.name}: ' + ', '.join(x for x,y in [('layers',p.add_layers),('OKRP',p.add_data)] if y))
            for backup in backups:
                self.write(f'Sauvegarde : {backup}')
            messagebox.showinfo('Terminé', f'{len(changes)} type(s) complété(s).\n{len(backups)} sauvegardes créées.\nLes XML existants ont été conservés.')
            self.analyze()
        except Exception as exc:
            self.write('ERREUR : ' + str(exc))
            messagebox.showerror('Erreur — aucun remplacement intentionnel', str(exc))

if __name__ == '__main__':
    Application().mainloop()
