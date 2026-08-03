import { Folders, Inbox, Receipt, CalendarClock, ClipboardList, MessageSquare, Globe } from 'lucide-react';
import Integrations from './components/Integrations';
import Invoices from './components/Invoices';
import Watches from './components/Watches';
import Tasks from './components/Tasks';
// Loaded when it is opened rather than at startup, and behind a boundary — see
// WebsiteWorkspace.jsx for why that is load-bearing rather than tidy.
import Website from './components/website/WebsiteWorkspace';

// Product workspaces are kept together so adding another desktop area means
// adding one definition, with navigation and rendering derived from it.
export const PRODUCT_WORKSPACES = [
  {
    id: 'integrations',
    label: 'Inkommande',
    icon: Inbox,
    render: ({ brfId, isAdmin, onOpenDocument, onDocumentsChanged }) => (
      <Integrations
        brfId={brfId}
        isAdmin={isAdmin}
        onOpenDocument={onOpenDocument}
        // A decision in the queue can put a document in the archive:
        // that is what "ta in" means. Without this the association's
        // own document list kept saying the message was not there.
        onDocumentsChanged={onDocumentsChanged}
      />
    ),
  },
  {
    id: 'invoices',
    label: 'Fakturor',
    icon: Receipt,
    render: ({ brfId, isAdmin, onOpenDocument, onOpenCitation }) => (
      <Invoices
        brfId={brfId}
        isAdmin={isAdmin}
        onOpenDocument={onOpenDocument}
        onOpenCitation={onOpenCitation}
      />
    ),
  },
  {
    id: 'watches',
    label: 'Bevakningar',
    icon: CalendarClock,
    render: ({ brfId, isAdmin, onOpenCitation }) => (
      <Watches
        brfId={brfId}
        isAdmin={isAdmin}
        onOpenCitation={onOpenCitation}
      />
    ),
  },
  {
    id: 'tasks',
    label: 'Uppgifter',
    icon: ClipboardList,
    render: ({ brfId, isAdmin, onOpenCitation }) => (
      <Tasks
        brfId={brfId}
        isAdmin={isAdmin}
        onOpenCitation={onOpenCitation}
      />
    ),
  },
  {
    id: 'website',
    label: 'Hemsidan',
    icon: Globe,
    render: ({ brfId, isAdmin, onOpenCitation }) => (
      <Website
        brfId={brfId}
        isAdmin={isAdmin}
        // Text the AI wrote out of the association's own documents keeps its
        // citations, and they open the PDF at the cited page like every other
        // piece of evidence in the product.
        onOpenCitation={onOpenCitation}
      />
    ),
  },
];

export const NAV_ITEMS = [
  { id: 'docs', label: 'Dokument', icon: Folders },
  { id: 'chat', label: 'AI-chatt', icon: MessageSquare },
  ...PRODUCT_WORKSPACES.map(({ id, label, icon }) => ({
    id,
    label,
    icon,
    desktopOnly: true,
  })),
];
