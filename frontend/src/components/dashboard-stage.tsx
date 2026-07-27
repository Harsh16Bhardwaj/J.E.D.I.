"use client";

import { motion, useReducedMotion } from "motion/react";

export function DashboardStage({ children }: { children: React.ReactNode }) {
  const reducedMotion = useReducedMotion();

  return (
    <motion.div
      initial={reducedMotion ? false : { opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: reducedMotion ? 0 : 0.28, ease: "easeOut" }}
      className="space-y-10"
    >
      {children}
    </motion.div>
  );
}
