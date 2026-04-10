import { useState, useEffect, useCallback } from 'react'
import ProjectBar from './components/ProjectBar.jsx'
import IntentMap from './components/IntentMap.jsx'
import FeatureView from './components/FeatureView.jsx'
import FunctionDetail from './components/FunctionDetail.jsx'
import SearchView from './components/SearchView.jsx'
import EvolutionTimeline from './components/EvolutionTimeline.jsx'
import ProjectInsights from './components/ProjectInsights.jsx'
import CoverageBar from './components/CoverageBar.jsx'
import ServerFooter from './components/ServerFooter.jsx'
import { apiFetch } from './api.js'
import s from './App.module.css'

const TABS = ['Intent Map', 'Features', 'Search', 'Timeline']

export default function App() {
  const [project, setProject] = useState(null)
  const [stats, setStats] = useState(null)
  const [map, setMap] = useState(null)
  const [activeTab, setActiveTab] = useState('Intent Map')
  const [selectedFn, setSelectedFn] = useState(null)
  const loadStats = useCallback(async (path) => {
    const r = await apiFetch(`/stats?project_path=${encodeURIComponent(path)}`)
    if (r.ok) setStats(await r.json())
  }, [])

  const loadMap = useCallback(async (path) => {
    const r = await apiFetch(`/map?project_path=${encodeURIComponent(path)}`)
    if (r.ok) setMap(await r.json())
  }, [])

  function onProjectLoaded(proj) {
    setProject(proj)
    setSelectedFn(null)
    loadStats(proj.path)
    loadMap(proj.path)
  }

  useEffect(() => {
    if (!project) return
    const t = setInterval(() => {
      loadStats(project.path)
      loadMap(project.path)
    }, 20000)
    return () => clearInterval(t)
  }, [project, loadStats, loadMap])

  return (
    <div className={s.layout}>
      <header className={s.header}>
        <div className={s.headerLeft}>
          <span className={s.logo}>◇ Own Your Code</span>
          <span className={s.tagline}>why your code exists — captured as you build · any MCP client</span>
        </div>
        <ProjectBar onLoaded={onProjectLoaded} current={project} />
      </header>

      {project && stats && (
        <CoverageBar
          total={stats.total}
          annotated={stats.annotated}
          coverage={stats.coverage}
          features={stats.features}
          unannotated={stats.unannotated_files}
          hookBacklog={stats.hook_backlog || []}
        />
      )}

      <div className={s.body}>
        {!project ? (
          <div className={s.splash}>
            <div className={s.splashIcon}>◇</div>
            <div className={s.splashTitle}>Own Your Code</div>
            <div className={s.splashSub}>
              A living map of why every function exists — user requests, tradeoffs, and evolution —
              <br />recorded via MCP as you work.
            </div>
            <div className={s.splashSteps}>
              <Step n="1" text="Register your project" />
              <Step n="2" text="Agent calls record_intent as it writes" />
              <Step n="3" text="Navigate by intent, not by file tree" />
            </div>
          </div>
        ) : (
          <>
            <aside className={s.sidebar}>
              {map && <ProjectInsights map={map} onSelect={setSelectedFn} />}
              <div className={s.tabs}>
                {TABS.map(t => (
                  <button
                    key={t}
                    className={`${s.tab} ${activeTab === t ? s.tabActive : ''}`}
                    onClick={() => setActiveTab(t)}
                  >
                    {t}
                  </button>
                ))}
              </div>

              <div className={s.tabContent}>
                {activeTab === 'Intent Map' && (
                  <IntentMap projectPath={project.path} selected={selectedFn} onSelect={setSelectedFn} />
                )}
                {activeTab === 'Features' && (
                  <FeatureView projectPath={project.path} onSelect={setSelectedFn} />
                )}
                {activeTab === 'Search' && (
                  <SearchView projectPath={project.path} onSelect={setSelectedFn} />
                )}
                {activeTab === 'Timeline' && (
                  <EvolutionTimeline projectPath={project.path} onSelect={setSelectedFn} />
                )}
              </div>
            </aside>

            <main className={s.main}>
              {selectedFn ? (
                <FunctionDetail
                  projectPath={project.path}
                  functionName={selectedFn}
                  onClose={() => setSelectedFn(null)}
                />
              ) : (
                <div className={s.mainEmpty}>
                  <div style={{ color: 'var(--text3)', fontSize: 14 }}>
                    Select a function to see why it exists
                  </div>
                </div>
              )}
            </main>
          </>
        )}
      </div>

      <ServerFooter
        onApiKeySaved={() => {
          if (project) {
            loadStats(project.path)
            loadMap(project.path)
          }
        }}
      />
    </div>
  )
}

function Step({ n, text }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
      <span style={{ width: 24, height: 24, borderRadius: '50%', background: 'var(--blue)', color: '#fff', fontSize: 12, fontWeight: 700, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>{n}</span>
      <span style={{ color: 'var(--text2)', fontSize: 13 }}>{text}</span>
    </div>
  )
}
