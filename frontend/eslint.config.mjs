import { dirname } from "path";
import { fileURLToPath } from "url";
import { FlatCompat } from "@eslint/eslintrc";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const compat = new FlatCompat({ baseDirectory: __dirname });

const config = [
  { ignores: [".next/**", "node_modules/**", "out/**", "next-env.d.ts"] },
  ...compat.extends("next/core-web-vitals", "next/typescript"),
  {
    rules: {
      // Privacy rule: resume, job-description and candidate data must never reach persistent
      // browser storage. See PRIVACY_ARCHITECTURE.md section 4.
      "no-restricted-globals": [
        "error",
        { name: "localStorage", message: "Persistent browser storage is forbidden for user data." },
        { name: "indexedDB", message: "Persistent browser storage is forbidden for user data." },
      ],
      "no-restricted-properties": [
        "error",
        { object: "window", property: "localStorage", message: "Persistent storage is forbidden." },
        { object: "window", property: "indexedDB", message: "Persistent storage is forbidden." },
      ],
      "react/no-danger": "error",
    },
  },
];

export default config;
