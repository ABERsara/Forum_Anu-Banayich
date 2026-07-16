/**
 * Application routing.
 *
 * All feature modules are lazy-loaded (loadComponent).
 * This keeps the initial bundle small.
 *
 * Route structure:
 *   Public:      /login, /register
 *   User:        /forum, /advice, /messages, /profile
 *   Admin:       /admin/**
 *   Moderator:   /moderator/**
 *   Professional: /professional/**
 */

import { Routes } from '@angular/router';

import { UserRole } from './core/constants';
import { authGuard } from './core/guards/auth.guard';
import { roleGuard } from './core/guards/role.guard';

export const routes: Routes = [
  // ──────────────────────────────────────────────────────────
  // Public routes
  // ──────────────────────────────────────────────────────────
  {
    path: '',
    redirectTo: '/home',
    pathMatch: 'full',
  },
  {
    path: 'home',
    canActivate: [authGuard],
    loadComponent: () => import('./features/home/home.component').then((m) => m.HomeComponent),
  },
  {
    path: 'login',
    loadComponent: () =>
      import('./features/auth/login/login.component').then((m) => m.LoginComponent),
  },
  {
    path: 'register',
    loadComponent: () =>
      import('./features/auth/register/register.component').then((m) => m.RegisterComponent),
  },
  {
    path: 'auth/pending',
    loadComponent: () =>
      import('./features/auth/pending/pending.component').then((m) => m.PendingApprovalComponent),
  },

  // ──────────────────────────────────────────────────────────
  // Protected – USER role
  // ──────────────────────────────────────────────────────────
  {
    path: 'forum',
    canActivate: [authGuard],
    children: [
      {
        path: '',
        loadComponent: () =>
          import('./features/forum/forum-list/forum-list.component').then(
            (m) => m.ForumListComponent,
          ),
      },
      {
        path: 'new',
        loadComponent: () =>
          import('./features/forum/new-post/new-post.component').then((m) => m.NewPostComponent),
      },
      {
        path: ':id/edit',
        loadComponent: () =>
          import('./features/forum/edit-post/edit-post.component').then((m) => m.EditPostComponent),
      },
      {
        path: ':id',
        loadComponent: () =>
          import('./features/forum/forum-post/forum-post.component').then(
            (m) => m.ForumPostComponent,
          ),
      },
    ],
  },
  {
    path: 'advice',
    canActivate: [authGuard],
    children: [
      {
        path: '',
        loadComponent: () =>
          import('./features/advice/advice-list/advice-list.component').then(
            (m) => m.AdviceListComponent,
          ),
      },
      {
        path: 'ask',
        loadComponent: () =>
          import('./features/advice/ask-question/ask-question.component').then(
            (m) => m.AskQuestionComponent,
          ),
      },
      {
        path: 'qa',
        loadComponent: () =>
          import('./features/advice/qa-feed/qa-feed.component').then((m) => m.QaFeedComponent),
      },
      {
        path: 'my-questions',
        loadComponent: () =>
          import('./features/advice/my-questions/my-questions.component').then(
            (m) => m.MyQuestionsComponent,
          ),
      },
    ],
  },
  {
    path: 'messages',
    canActivate: [authGuard],
    children: [
      {
        path: '',
        loadComponent: () =>
          import('./features/messages/inbox/inbox.component').then((m) => m.InboxComponent),
      },
      {
        path: ':userId',
        loadComponent: () =>
          import('./features/messages/chat/chat.component').then((m) => m.ChatComponent),
      },
    ],
  },
  {
    path: 'profile',
    canActivate: [authGuard],
    loadComponent: () =>
      import('./features/profile/profile.component').then((m) => m.ProfileComponent),
  },

  // ──────────────────────────────────────────────────────────
  // Admin routes
  // ──────────────────────────────────────────────────────────
  {
    path: 'admin',
    canActivate: [authGuard, roleGuard(UserRole.ADMIN)],
    children: [
      {
        path: '',
        loadComponent: () =>
          import('./features/admin/dashboard/admin-dashboard.component').then(
            (m) => m.AdminDashboardComponent,
          ),
      },
      {
        path: 'registrations',
        loadComponent: () =>
          import('./features/admin/pending-registrations/pending-registrations.component').then(
            (m) => m.PendingRegistrationsComponent,
          ),
      },
      {
        path: 'professionals',
        loadComponent: () =>
          import('./features/admin/manage-professionals/manage-professionals.component').then(
            (m) => m.ManageProfessionalsComponent,
          ),
      },
      {
        path: 'audit-log',
        loadComponent: () =>
          import('./features/admin/audit-log/audit-log.component').then((m) => m.AuditLogComponent),
      },
      {
        path: 'active-users',
        loadComponent: () =>
          import('./features/admin/active-users/active-users.component').then(
            (m) => m.ActiveUsersComponent,
          ),
      },
    ],
  },

  // ──────────────────────────────────────────────────────────
  // Moderator routes
  // ──────────────────────────────────────────────────────────
  {
    path: 'moderator',
    canActivate: [authGuard, roleGuard(UserRole.MODERATOR, UserRole.ADMIN)],
    children: [
      {
        path: '',
        redirectTo: 'reports',
        pathMatch: 'full',
      },
      {
        path: 'reports',
        loadComponent: () =>
          import('./features/moderator/reports/reports.component').then(
            (m) => m.ModeratorReportsComponent,
          ),
      },
    ],
  },

  // ──────────────────────────────────────────────────────────
  // Fallback
  // ──────────────────────────────────────────────────────────
  {
    path: '**',
    redirectTo: '/home',
  },
];
