(() => {
  const messages = window.OPUS_I18N?.messages;
  if (!messages) return;
  Object.assign(messages.en, {
    'validation.valid':'VALID',
    'validation.invalid':'INVALID',
    'validation.error':'VALIDATOR ERROR',
    'validation.details':'Validator details',
    'validation.output':'View validator output',
    'validation.noIssues':'No validator issue reported.',
    'validation.noOutput':'No raw output.'
  });
  Object.assign(messages.fr, {
    'validation.valid':'VALIDE',
    'validation.invalid':'INVALIDE',
    'validation.error':'ERREUR DU VALIDATEUR',
    'validation.details':'Détails du validateur',
    'validation.output':'Voir la sortie du validateur',
    'validation.noIssues':'Aucun problème signalé par le validateur.',
    'validation.noOutput':'Aucune sortie brute.'
  });
})();
