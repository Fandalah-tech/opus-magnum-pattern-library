(() => {
  const en = window.OPUS_I18N.messages.en;
  const fr = window.OPUS_I18N.messages.fr;
  Object.assign(en, {
    'inspector.diagnostics':'Optimization diagnostics','inspector.diagnosticsHint':'Static, explainable opportunities. Every proposed change must still be validated by omsim.','inspector.diagnosticCount':'diagnostics','inspector.noDiagnostics':'No static optimization issue detected.','severity.warning':'Warning','severity.opportunity':'Opportunity','severity.info':'Information',
    'diagnostic.high-global-idle-time':'High global idle time','diagnostic.very-low-arm-utilization':'Very low arm utilization','diagnostic.unbalanced-arm-workload':'Unbalanced arm workload','diagnostic.no-observed-program-parallelism':'No observed program parallelism','diagnostic.bursty-parallelism':'Bursty parallelism','diagnostic.divergent-arm-periods':'Divergent arm periods','diagnostic.independent-components-available':'Independent components available','diagnostic.sparse-arms-without-parallel-scheduling':'Sparse arms without parallel scheduling'
  });
  Object.assign(fr, {
    'inspector.diagnostics':'Diagnostics d’optimisation','inspector.diagnosticsHint':'Occasions statiques et explicables. Toute modification proposée doit encore être validée par omsim.','inspector.diagnosticCount':'diagnostics','inspector.noDiagnostics':'Aucun enjeu statique d’optimisation détecté.','severity.warning':'Avertissement','severity.opportunity':'Occasion','severity.info':'Information',
    'diagnostic.high-global-idle-time':'Temps mort global élevé','diagnostic.very-low-arm-utilization':'Très faible utilisation d’un bras','diagnostic.unbalanced-arm-workload':'Charge de travail déséquilibrée','diagnostic.no-observed-program-parallelism':'Aucun parallélisme observé','diagnostic.bursty-parallelism':'Parallélisme concentré','diagnostic.divergent-arm-periods':'Périodes de bras divergentes','diagnostic.independent-components-available':'Composantes indépendantes disponibles','diagnostic.sparse-arms-without-parallel-scheduling':'Bras peu actifs sans planification parallèle'
  });
})();
