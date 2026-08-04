(() => {
  const messages = window.OPUS_I18N?.messages;
  if (!messages) return;
  Object.assign(messages.en, {
    'viewer.title':'Solution viewer',
    'viewer.hint':'Select a part to inspect it. Drag to pan and use the mouse wheel to zoom.',
    'viewer.fit':'Fit',
    'viewer.reset':'Reset',
    'viewer.select':'Select a part on the map.'
  });
  Object.assign(messages.fr, {
    'viewer.title':'Visualiseur de solution',
    'viewer.hint':'Sélectionne une pièce pour l’inspecter. Fais glisser pour déplacer la vue et utilise la molette pour zoomer.',
    'viewer.fit':'Ajuster',
    'viewer.reset':'Réinitialiser',
    'viewer.select':'Sélectionne une pièce sur la carte.'
  });
})();
