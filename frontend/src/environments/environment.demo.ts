import { getApiBaseUrl } from '../app/core/config/api.config';

export const environment = {
  production: true,
  apiBaseUrl: getApiBaseUrl(),
  portal: 'demo'
};
