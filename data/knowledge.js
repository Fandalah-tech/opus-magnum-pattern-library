window.OPUS_CONCEPTS=[
{id:'concept-transmutation',name:'Transmutation',definition:'Transformer un atome en un autre niveau métallique au moyen d’un glyphe.',principles:['entrée contrôlée','positionnement sur glyphe','évacuation'],patternIds:['single-projection','double-projection']},
{id:'concept-shared-motion',name:'Mouvement partagé',definition:'Réutiliser un même axe, bras ou espace de rotation pour plusieurs fonctions.',principles:['réduction du coût','réduction de l’empreinte','conflits temporels possibles'],patternIds:['shared-axis']},
{id:'concept-handoff',name:'Passage de relais',definition:'Transférer une molécule entre deux sous-systèmes à une position et un instant compatibles.',principles:['fenêtre commune','orientation compatible','synchronisation'],patternIds:['handoff']},
{id:'concept-buffering',name:'Découplage par tampon',definition:'Absorber une différence de cadence entre deux modules grâce à un stockage temporaire.',principles:['capacité','latence','robustesse'],patternIds:['loop-buffer']},
{id:'concept-symmetry',name:'Symétrie exploitable',definition:'Utiliser la symétrie du produit ou des réactifs pour réduire les mouvements et simplifier l’assemblage.',principles:['flux jumeaux','point de convergence','instructions parallèles'],patternIds:['mirror-assembler']}
];

window.OPUS_IMPLEMENTATIONS=[
{id:'impl-single-projection-demo',patternId:'single-projection',name:'Démonstrateur pédagogique',status:'prototype',metrics:{cost:35,area:9,cycles:8},author:'Opus Magnus Research',puzzle:null,evidence:null,notes:'Valeurs fictives utilisées uniquement pour valider l’interface.'},
{id:'impl-double-projection-demo',patternId:'double-projection',name:'Chaîne à axe rapproché',status:'prototype',metrics:{cost:65,area:14,cycles:12},author:'Opus Magnus Research',puzzle:null,evidence:null,notes:'Doit être remplacée par une implémentation issue d’une vraie solution.'},
{id:'impl-shared-axis-demo',patternId:'shared-axis',name:'Axe triple fonction',status:'conceptual',metrics:{cost:40,area:11,cycles:10},author:'Opus Magnus Research',puzzle:null,evidence:null,notes:'Illustration conceptuelle, non mesurée en jeu.'},
{id:'impl-handoff-demo',patternId:'handoff',name:'Relais deux bras',status:'conceptual',metrics:{cost:40,area:12,cycles:6},author:'Opus Magnus Research',puzzle:null,evidence:null,notes:'Illustration conceptuelle, non mesurée en jeu.'},
{id:'impl-loop-buffer-demo',patternId:'loop-buffer',name:'Tampon circulaire',status:'conceptual',metrics:{cost:50,area:18,cycles:9},author:'Opus Magnus Research',puzzle:null,evidence:null,notes:'Illustration conceptuelle, non mesurée en jeu.'},
{id:'impl-mirror-demo',patternId:'mirror-assembler',name:'Convergence symétrique',status:'prototype',metrics:{cost:80,area:20,cycles:14},author:'Opus Magnus Research',puzzle:null,evidence:null,notes:'Valeurs fictives utilisées uniquement pour valider l’interface.'}
];
