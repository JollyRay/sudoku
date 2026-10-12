GridStack 14.0.0, npm distribution, MIT license in LICENSE.

Source: https://github.com/gridstack/gridstack.js/releases/tag/v14.0.0
Files downloaded from https://cdn.jsdelivr.net/npm/gridstack@14.0.0/
(`dist/gridstack-all.js`, `dist/gridstack.min.css`, `LICENSE`).
Loaded locally; no runtime CDN dependency.

Local change: removed the trailing `sourceMappingURL` comment from
`gridstack-all.js` because its source map is not vendored. This allows Django's
`ManifestStaticFilesStorage` to run `collectstatic` without a missing-file error.
The executable JavaScript is unchanged.
