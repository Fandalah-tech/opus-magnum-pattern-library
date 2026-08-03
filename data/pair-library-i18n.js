(() => {
  const messages = window.OPUS_I18N?.messages;
  if (!messages) return;
  Object.assign(messages.en, {
    'library.title':'Recent pairs',
    'library.description':'Pairs are stored privately in this browser for faster repeat testing.',
    'library.empty':'No saved pair yet',
    'library.load':'Load pair',
    'library.rename':'Rename',
    'library.delete':'Delete',
    'library.saved':'Pair saved in this browser.',
    'library.loaded':'Saved pair loaded.',
    'library.deleted':'Saved pair deleted.',
    'library.renamePrompt':'New name for this pair:',
    'library.storageError':'Browser storage is unavailable.'
  });
  Object.assign(messages.fr, {
    'library.title':'Paires récentes',
    'library.description':'Les paires sont conservées localement et confidentiellement dans ce navigateur pour accélérer les tests répétés.',
    'library.empty':'Aucune paire enregistrée',
    'library.load':'Charger la paire',
    'library.rename':'Renommer',
    'library.delete':'Supprimer',
    'library.saved':'Paire enregistrée dans ce navigateur.',
    'library.loaded':'Paire enregistrée chargée.',
    'library.deleted':'Paire enregistrée supprimée.',
    'library.renamePrompt':'Nouveau nom pour cette paire :',
    'library.storageError':'Le stockage du navigateur est indisponible.'
  });
})();
