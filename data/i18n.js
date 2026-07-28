window.OPUS_I18N={
  defaultLocale:'en',
  supportedLocales:['en','fr'],
  messages:{
    en:{
      'app.title':'Pattern Library','app.documented':'patterns documented','nav.patterns':'Patterns','nav.concepts':'Concepts','nav.relations':'Relations','search.placeholder':'Search patterns…','filters.categories':'Categories','filters.objectives':'Objectives','filters.all':'All','actions.reset':'Reset','view.explorer':'Explorer','view.allPatterns':'All patterns','view.concepts':'Concepts','view.relations':'Knowledge graph','empty.title':'No pattern found','empty.body':'Change the filters or search term.','detail.requirements':'Requirements','detail.relations':'Relations','detail.implementations':'Implementations','detail.concept':'Parent concept','metric.cost':'Cost','metric.area':'Area','metric.cycles':'Cycles','status.prototype':'prototype','status.concept':'concept','status.conceptual':'conceptual','term.provisional':'Provisional research term','language.en':'English','language.fr':'Français'
    },
    fr:{
      'app.title':'Bibliothèque de patterns','app.documented':'patterns documentés','nav.patterns':'Patterns','nav.concepts':'Concepts','nav.relations':'Relations','search.placeholder':'Rechercher un pattern…','filters.categories':'Catégories','filters.objectives':'Objectifs','filters.all':'Tous','actions.reset':'Réinitialiser','view.explorer':'Explorateur','view.allPatterns':'Tous les patterns','view.concepts':'Concepts','view.relations':'Graphe de connaissances','empty.title':'Aucun pattern trouvé','empty.body':'Modifie les filtres ou le terme de recherche.','detail.requirements':'Prérequis','detail.relations':'Relations','detail.implementations':'Implémentations','detail.concept':'Concept parent','metric.cost':'Coût','metric.area':'Area','metric.cycles':'Cycles','status.prototype':'prototype','status.concept':'concept','status.conceptual':'conceptuel','term.provisional':'Terme de recherche provisoire','language.en':'English','language.fr':'Français'
    }
  }
};

window.OpusI18n={
  locale:localStorage.getItem('opus-locale')||window.OPUS_I18N.defaultLocale,
  t(key){return window.OPUS_I18N.messages[this.locale]?.[key]||window.OPUS_I18N.messages.en[key]||key;},
  setLocale(locale){if(!window.OPUS_I18N.supportedLocales.includes(locale))return;this.locale=locale;localStorage.setItem('opus-locale',locale);document.documentElement.lang=locale==='fr'?'fr-CA':'en';window.dispatchEvent(new CustomEvent('opus:localechange'));}
};