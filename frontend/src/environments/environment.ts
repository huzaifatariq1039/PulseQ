import { getApiBaseUrl } from '../app/core/config/api.config';

export const environment = {
  production: false,
  apiBaseUrl: getApiBaseUrl(),
  portal: 'main'
};
