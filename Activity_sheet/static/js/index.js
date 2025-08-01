    async function loadCinnosti() {
      const response = await fetch('/api/cinnosti');
      const data = await response.json();
      const container = document.getElementById('cinnosti-container');
      container.innerHTML = '';

      data.sekce.forEach(sekce => {
        const sekceDiv = document.createElement('section');
        const nadpis = document.createElement('h2');
        nadpis.textContent = `${sekce.nazev} (${sekce.cinnosti.length})`;
        sekceDiv.appendChild(nadpis);

        const contentDiv = document.createElement('div');
        contentDiv.className = 'content';

        sekce.cinnosti.forEach(cinnost => {
          const div = document.createElement('div');
          div.className = 'cinnost';

          const label = document.createElement('div');
          label.textContent = `${cinnost.nazev} (ID: ${cinnost.id})`;

          const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
          svg.id = `barcode-${cinnost.id.replace(/[^a-zA-Z0-9]/g, '')}`;

          div.appendChild(label);
          div.appendChild(svg);
          contentDiv.appendChild(div);

          JsBarcode(svg, cinnost.id, {
            format: "code128",
            width: 2,
            height: 50,
            displayValue: false
          });

          div.addEventListener('click', () => openModal(cinnost));
        });

        sekceDiv.appendChild(contentDiv);
        container.appendChild(sekceDiv);

        nadpis.addEventListener('click', () => {
          contentDiv.classList.toggle('active');
        });
      });

      const toggleAllBtn = document.getElementById('toggleAllBtn');
      toggleAllBtn.onclick = () => {
        const vsechnyObsahy = document.querySelectorAll('.content');
        const necoNeniAktivni = Array.from(vsechnyObsahy).some(div => !div.classList.contains('active'));
        vsechnyObsahy.forEach(div => {
          div.classList.toggle('active', necoNeniAktivni);
        });
        toggleAllBtn.textContent = necoNeniAktivni ? 'Sbalit všechny sekce' : 'Rozbalit všechny sekce';
      };
    }

    function openModal(cinnost) {
      const modal = document.getElementById('modal');
      const modalBarcode = document.getElementById('modal-barcode');
      const modalLabel = document.getElementById('modal-label');
      const modalIframe = document.getElementById('modal-iframe');

      modalBarcode.innerHTML = '';
      modalLabel.textContent = `${cinnost.nazev} (ID: ${cinnost.id})`;

      const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
      svg.id = `modal-barcode-svg`;
      modalBarcode.appendChild(svg);

      JsBarcode(svg, cinnost.id, {
        format: "code128",
        width: 4,
        height: 100,
        displayValue: true,
        fontSize: 18
      });

      modalIframe.src = `https://example.com?id=${encodeURIComponent(cinnost.id)}`;  //<-------  Replace (https://example.com) with your aplikation URL
      modal.classList.add('active');
    }

    document.getElementById('modal-close').addEventListener('click', () => {
      document.getElementById('modal').classList.remove('active');
    });

    document.getElementById('modal').addEventListener('click', e => {
      if (e.target === e.currentTarget) {
        document.getElementById('modal').classList.remove('active');
      }
    });

    document.getElementById('open-end-modal').addEventListener('click', () => {
      document.getElementById('modal-end').classList.add('active');
    });

    document.getElementById('modal-end-close').addEventListener('click', () => {
      document.getElementById('modal-end').classList.remove('active');
    });

    document.getElementById('modal-end').addEventListener('click', (e) => {
      if (e.target === e.currentTarget) {
        document.getElementById('modal-end').classList.remove('active');
      }
    });

    loadCinnosti();