// Adds secrets that must not live in app.json. The Google Maps key for the hardware-store map comes from the
// EAS environment variable GOOGLE_MAPS_ANDROID_API_KEY (set it in expo.dev > project > Environment variables).
module.exports = ({ config }) => {
  const key = process.env.GOOGLE_MAPS_ANDROID_API_KEY;
  return {
    ...config,
    android: {
      ...config.android,
      config: { ...(config.android?.config ?? {}), ...(key ? { googleMaps: { apiKey: key } } : {}) },
    },
  };
};
