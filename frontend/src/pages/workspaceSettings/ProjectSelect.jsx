import React, { useId } from "react";

/** A labelled choice of project for a dialog; `projects` are the workspace's. */
export function ProjectSelect({ projects, value, onChange, label = "Project", hint }) {
  const id = useId();
  return (
    <div className="field">
      <label className="field__label" htmlFor={id}>
        {label}
      </label>
      <select id={id} className="field__input" value={value} onChange={(event) => onChange(event.target.value)}>
        {projects.map((project) => (
          <option key={project.id} value={project.id}>
            {project.name}
          </option>
        ))}
      </select>
      {hint ? <span className="field__hint">{hint}</span> : null}
    </div>
  );
}
