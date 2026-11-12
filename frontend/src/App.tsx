import { useEffect, useState } from 'react';
import { Menu } from 'lucide-react';
import { api } from './api/client';
import type { HealthResponse, NavSectionId } from './types/api';
import { NAV_ITEMS, Sidebar } from './components/common/Sidebar';
import { ChampionsLeagueSection } from './sections/ChampionsLeagueSection';
import { DomesticPerformanceSection } from './sections/DomesticPerformanceSection';
import { MarketValueSection } from './sections/MarketValueSection';
import { MethodologySection } from './sections/MethodologySection';
import { OverviewSection } from './sections/OverviewSection';
import { PlayerComparisonSection } from './sections/PlayerComparisonSection';
import { PlayerIntelligenceSection } from './sections/PlayerIntelligenceSection';
import { StatisticalInsightsSection } from './sections/StatisticalInsightsSection';
import { TransferMarketSection } from './sections/TransferMarketSection';
import { TransferValueCalculatorSection } from './sections/TransferValueCalculatorSection';

const VALID_SECTIONS = new Set<NavSectionId>(NAV_ITEMS.map((item) => item.id));

function readInitialSection(): NavSectionId {
  const hash = window.location.hash.replace(/^#/, '') as NavSectionId;
  return VALID_SECTIONS.has(hash) ? hash : 'overview';
}

export function App() {
  const [activeSection, setActiveSection] = useState<NavSectionId>(readInitialSection);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [apiOnline, setApiOnline] = useState<boolean>(false);
  const [mobileOpen, setMobileOpen] = useState<boolean>(false);
  const [selectedPlayerId, setSelectedPlayerId] = useState<number>(342229);
  const [comparePlayerId, setComparePlayerId] = useState<number | null>(null);
  const [calcPlayerId, setCalcPlayerId] = useState<number | null>(null);

  useEffect(() => {
    const ctrl = new AbortController();
    api
      .getHealth(ctrl.signal)
      .then((res) => {
        setHealth(res);
        setApiOnline(res.status === 'ok' && res.database_connected);
      })
      .catch(() => {
        setApiOnline(false);
      });
    return () => ctrl.abort();
  }, []);

  const handleSelectSection = (id: NavSectionId) => {
    setActiveSection(id);
    window.history.replaceState(null, '', `#${id}`);
  };

  const currentNav = NAV_ITEMS.find((item) => item.id === activeSection) ?? NAV_ITEMS[0];

  return (
    <div className="app-shell">
      <Sidebar
        activeSection={activeSection}
        onSelect={handleSelectSection}
        health={health}
        apiOnline={apiOnline}
        mobileOpen={mobileOpen}
        onCloseMobile={() => setMobileOpen(false)}
      />

      <div className="main-wrap">
        <header className="topbar">
          <div className="topbar-left">
            <button
              type="button"
              className="mobile-menu-btn"
              aria-label="Open navigation menu"
              onClick={() => setMobileOpen(true)}
            >
              <Menu size={18} />
            </button>
            <div>
              <h1 className="page-title">{currentNav.label}</h1>
              <p className="page-subtitle">{currentNav.subtitle}</p>
            </div>
          </div>

          <div className="topbar-badge" title={`API Base: ${api.baseUrl}`}>
            {health ? `DuckDB • 2012/13–2025/26` : 'FastAPI Data Engine'}
          </div>
        </header>

        <main className="content-area">
          {activeSection === 'overview' && <OverviewSection />}
          {activeSection === 'market' && <TransferMarketSection />}
          {activeSection === 'domestic' && <DomesticPerformanceSection />}
          {activeSection === 'ucl' && <ChampionsLeagueSection />}
          {activeSection === 'value' && <MarketValueSection />}
          {activeSection === 'statistics' && <StatisticalInsightsSection />}
          {activeSection === 'players' && (
            <PlayerIntelligenceSection
              selectedPlayerId={selectedPlayerId}
              onSelectPlayerId={setSelectedPlayerId}
              onOpenComparison={(id) => {
                setComparePlayerId(id);
                handleSelectSection('player-compare');
              }}
              onOpenCalculator={(id) => {
                setCalcPlayerId(id);
                handleSelectSection('calculator');
              }}
            />
          )}
          {activeSection === 'player-compare' && (
            <PlayerComparisonSection initialPlayerId={comparePlayerId} />
          )}
          {activeSection === 'calculator' && (
            <TransferValueCalculatorSection initialPlayerId={calcPlayerId} />
          )}
          {activeSection === 'methodology' && <MethodologySection />}
        </main>
      </div>
    </div>
  );
}

export default App;
