(() => {
  const hex = '<path d="M25 0h50l25 43-25 43H25L0 43Z"/>';
  const grid = `<g class="board-grid" opacity=".22" stroke="#74613c" fill="none" stroke-width="1.2">${[[-10,8],[72,8],[154,8],[236,8],[31,79],[113,79],[195,79],[277,79]].map(([x,y])=>`<g transform="translate(${x} ${y}) scale(.72)">${hex}</g>`).join('')}</g>`;
  const atom=(x,y,label,fill,stroke='#ead9a7')=>`<g transform="translate(${x} ${y})"><circle r="23" fill="#20190f" stroke="${stroke}" stroke-width="4"/><circle r="17" fill="${fill}" stroke="#75613b" stroke-width="2"/><text text-anchor="middle" y="5" font-family="Georgia,serif" font-size="13" fill="#3d2c17">${label}</text></g>`;
  const arm=(x,y,angle=0,length=70)=>`<g transform="translate(${x} ${y}) rotate(${angle})"><circle r="19" fill="#8c6d2d" stroke="#ead9a7" stroke-width="3"/><circle r="7" fill="#251c10" stroke="#d6b45d" stroke-width="2"/><path d="M8 0H${length}" stroke="#d7b55b" stroke-width="12" stroke-linecap="round"/><path d="M8 0H${length}" stroke="#5d4824" stroke-width="3" stroke-linecap="round"/><path d="M${length-4} -9l17 9-17 9" fill="#d7b55b" stroke="#ead9a7" stroke-width="2"/></g>`;
  const projection=(x,y)=>`<g transform="translate(${x} ${y})"><circle r="33" fill="#251b10" stroke="#e1bd62" stroke-width="4"/><circle r="19" fill="none" stroke="#9f7d35" stroke-width="3"/><path d="M0-38v76M-33 0h66M-23-23l46 46M23-23l-46 46" stroke="#e1bd62" stroke-width="3"/><path d="M0-47l7 10H-7Z" fill="#ead9a7"/></g>`;
  const bonding=(x,y)=>`<g transform="translate(${x} ${y})"><circle r="30" fill="#241b10" stroke="#e1bd62" stroke-width="4"/><circle cx="-12" cy="0" r="8" fill="none" stroke="#e1bd62" stroke-width="3"/><circle cx="12" cy="0" r="8" fill="none" stroke="#e1bd62" stroke-width="3"/><path d="M-4 0h8" stroke="#ead9a7" stroke-width="4"/></g>`;
  const track=(x,y,w=160)=>`<g transform="translate(${x} ${y})"><path d="M0 0H${w}" stroke="#8e6b2e" stroke-width="13" stroke-linecap="round"/><path d="M0 0H${w}" stroke="#d5b45b" stroke-width="4" stroke-dasharray="8 8" stroke-linecap="round"/></g>`;
  const wrap=body=>`<svg viewBox="0 0 360 210" xmlns="http://www.w3.org/2000/svg" role="img"><rect width="360" height="210" fill="#0f0d09"/>${grid}${body}</svg>`;

  window.OPUS_VISUALS = {
    projection: wrap(`${atom(62,110,'Pb','#a9c98e')}${arm(110,110,-8,92)}${projection(245,95)}${atom(245,95,'Sn','#c99562','#f2dfb4')}`),
    double: wrap(`${atom(38,115,'Pb','#a9c98e')}${arm(82,115,-10,70)}${projection(170,92)}${arm(205,118,-8,65)}${projection(300,90)}${atom(300,90,'Fe','#8b8f92','#e8d9b0')}`),
    axis: wrap(`${arm(180,108,-145,78)}${arm(180,108,-25,88)}${arm(180,108,92,70)}${atom(92,62,'Hg','#b8c9d1')}${atom(285,70,'Cu','#bd7441')}${atom(175,182,'Au','#d9b84f')}`),
    handoff: wrap(`${arm(95,110,-8,72)}${arm(265,110,188,72)}${atom(180,98,'Fe','#8b8f92','#e8d9b0')}${bonding(180,155)}`),
    loop: wrap(`${track(70,55,220)}${track(290,55,95)}${track(70,155,220)}${arm(95,105,-90,48)}${arm(265,105,90,48)}${atom(70,55,'Pb','#a9c98e')}${atom(290,155,'Sn','#c99562')}`),
    mirror: wrap(`${arm(92,116,-28,82)}${arm(268,116,208,82)}${atom(44,92,'Cu','#bd7441')}${atom(316,92,'Cu','#bd7441')}${bonding(180,122)}${atom(180,176,'Ag','#c9c9c6')}`)
  };
})();