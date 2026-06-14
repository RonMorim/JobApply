// Seed data for the dashboard prototype

const AGENTS = [
  {
    id: 'SCR-01', name: 'Scraper', role: 'Discovers postings across 14 sources',
    state: 'active',
    currentTask: 'Crawling LinkedIn · "Senior Product Designer" · page 4/12',
    stats: { today: 312, queue: 48, spark: [4,7,5,9,12,8,11,14,10,13,15,12] },
  },
  {
    id: 'ANL-01', name: 'Analyzer', role: 'Extracts structured signals from JDs',
    state: 'active',
    currentTask: 'Parsing 12 postings — tokenizing requirements & comp bands',
    stats: { today: 287, queue: 23, spark: [2,4,3,5,6,7,5,8,9,7,10,12] },
  },
  {
    id: 'MTC-01', name: 'Matcher', role: 'Ranks fit against your profile',
    state: 'queued',
    queueMsg: 'Rebuilding embeddings after resume update — resumes in 2m',
    stats: { today: 184, queue: 61, spark: [1,2,2,3,3,4,3,2,1,2,3,2] },
  },
  {
    id: 'APP-01', name: 'Applier', role: 'Submits applications with tailored materials',
    state: 'idle',
    stats: { today: 12, queue: 6, spark: [0,1,0,2,1,3,2,1,2,3,1,0] },
  },
];

window.AGENTS = AGENTS;
