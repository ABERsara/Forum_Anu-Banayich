import { inject } from '@angular/core';
import { Router, type CanActivateFn } from '@angular/router';

import { AccountStatus } from '../constants';
import { AuthService } from '../services/auth.service';

const PENDING_STATUSES: AccountStatus[] = [
  AccountStatus.PENDING_APPROVAL,
  AccountStatus.PARTIALLY_APPROVED,
];

export const authGuard: CanActivateFn = () => {
  const router = inject(Router);
  const auth = inject(AuthService);
  const token = localStorage.getItem('access_token');

  if (!token) {
    router.navigate(['/login']);
    return false;
  }

  const user = auth.currentUser();
  if (user && PENDING_STATUSES.includes(user.account_status)) {
    router.navigate(['/auth/pending']);
    return false;
  }

  return true;
};
