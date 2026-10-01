type LogLevel = 'debug' | 'info' | 'warn' | 'error' | 'silent';

const LEVELS: Record<LogLevel, number> = {
  debug: 10,
  info: 20,
  warn: 30,
  error: 40,
  silent: 100,
};

const configuredLevel: LogLevel = (import.meta.env.VITE_LOG_LEVEL as LogLevel) || 'info';
const currentLevelValue = LEVELS[configuredLevel] || LEVELS.info;

class Logger {
  private async relay(level: 'warn' | 'error', namespace: string, msg: string, data?: Record<string, any>) {
    try {
      await fetch('/api/ui-log', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          level,
          namespace,
          msg,
          data,
          path: window.location.pathname,
        }),
      });
    } catch (err) {
      // Ignore network errors when sending logs to avoid infinite loops
    }
  }

  private log(level: LogLevel, namespace: string, msg: string, data?: Record<string, any>) {
    if (LEVELS[level] < currentLevelValue) return;

    const timestamp = new Date().toISOString();
    const logPrefix = `[${timestamp}] [${level.toUpperCase()}] ${namespace} — ${msg}`;
    
    if (data) {
      console[level === 'error' || level === 'warn' ? level : 'log'](logPrefix, data);
    } else {
      console[level === 'error' || level === 'warn' ? level : 'log'](logPrefix);
    }

    if (level === 'warn' || level === 'error') {
      this.relay(level, namespace, msg, data);
    }
  }

  debug(namespace: string, msg: string, data?: Record<string, any>) {
    this.log('debug', namespace, msg, data);
  }

  info(namespace: string, msg: string, data?: Record<string, any>) {
    this.log('info', namespace, msg, data);
  }

  warn(namespace: string, msg: string, data?: Record<string, any>) {
    this.log('warn', namespace, msg, data);
  }

  error(namespace: string, msg: string, data?: Record<string, any>) {
    this.log('error', namespace, msg, data);
  }
}

const logger = new Logger();
logger.info('logger', 'Logger initialised', { activeLevel: configuredLevel });

export default logger;
