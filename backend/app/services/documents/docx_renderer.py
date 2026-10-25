"""DOCX document renderer for resumes and cover letters using python-docx.

Supports modern, classic, and technical formatting styles with clean typography,
bullet points, and structured section layout.
"""

import io
from typing import Any
import docx
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from app.services.documents.schemas import StructuredCoverLetter, StructuredResume


class DocxRenderer:
    """Renders structured resume and cover letter data into downloadable Microsoft Word (.docx) files."""

    @staticmethod
    def render_resume(resume_data: StructuredResume | dict[str, Any], template_id: str = "modern") -> bytes:
        """Renders a structured resume into a styled .docx byte buffer."""
        if isinstance(resume_data, dict):
            resume = StructuredResume.model_validate(resume_data)
        else:
            resume = resume_data

        doc = docx.Document()

        # Set page margins (0.75 in standard)
        for section in doc.sections:
            section.top_margin = Inches(0.75)
            section.bottom_margin = Inches(0.75)
            section.left_margin = Inches(0.75)
            section.right_margin = Inches(0.75)

        # Style colors
        primary_color = RGBColor(30, 58, 138) if template_id == "modern" else (
            RGBColor(15, 23, 42) if template_id == "technical" else RGBColor(0, 0, 0)
        )

        # Candidate Name Heading
        title_p = doc.add_paragraph()
        title_run = title_p.add_run(resume.full_name)
        title_run.font.size = Pt(22)
        title_run.font.bold = True
        title_run.font.color.rgb = primary_color
        title_p.paragraph_format.space_after = Pt(2)

        # Contact info
        contact_parts = [resume.email]
        if resume.phone:
            contact_parts.append(resume.phone)
        if resume.location:
            contact_parts.append(resume.location)
        if resume.linkedin_url:
            contact_parts.append(resume.linkedin_url)
        if resume.github_url:
            contact_parts.append(resume.github_url)

        contact_p = doc.add_paragraph(" | ".join(contact_parts))
        contact_p.paragraph_format.space_after = Pt(8)
        contact_p.runs[0].font.size = Pt(9.5)
        contact_p.runs[0].font.color.rgb = RGBColor(100, 116, 139)

        # Target job header
        target_p = doc.add_paragraph()
        target_run = target_p.add_run(f"Target Role: {resume.target_title} • {resume.target_company}")
        target_run.font.size = Pt(10)
        target_run.font.bold = True
        target_run.font.color.rgb = primary_color
        target_p.paragraph_format.space_after = Pt(12)

        # Professional Summary
        if resume.professional_summary:
            DocxRenderer._add_heading(doc, "PROFESSIONAL SUMMARY", primary_color)
            sum_p = doc.add_paragraph(resume.professional_summary)
            sum_p.paragraph_format.space_after = Pt(10)
            sum_p.runs[0].font.size = Pt(10)

        # Skills
        if resume.highlighted_skills:
            DocxRenderer._add_heading(doc, "CORE SKILLS & TECHNOLOGIES", primary_color)
            skills_p = doc.add_paragraph(" • ".join(resume.highlighted_skills))
            skills_p.paragraph_format.space_after = Pt(10)
            skills_p.runs[0].font.size = Pt(10)

        # Experience
        if resume.experience:
            DocxRenderer._add_heading(doc, "PROFESSIONAL EXPERIENCE", primary_color)
            for exp in resume.experience:
                exp_header = doc.add_paragraph()
                title_r = exp_header.add_run(exp.title)
                title_r.font.bold = True
                title_r.font.size = Pt(10.5)

                co_r = exp_header.add_run(f" | {exp.company}")
                co_r.font.size = Pt(10.5)
                co_r.font.color.rgb = primary_color

                date_r = exp_header.add_run(f" ({exp.start_date} – {exp.end_date})")
                date_r.font.size = Pt(9.5)
                date_r.font.italic = True
                date_r.font.color.rgb = RGBColor(100, 116, 139)

                exp_header.paragraph_format.space_after = Pt(2)

                for bullet in exp.bullets:
                    b_p = doc.add_paragraph(bullet, style="List Bullet")
                    b_p.paragraph_format.space_after = Pt(2)
                    if b_p.runs:
                        b_p.runs[0].font.size = Pt(9.5)

                doc.add_paragraph().paragraph_format.space_after = Pt(4)

        # Projects
        if resume.projects:
            DocxRenderer._add_heading(doc, "KEY PROJECTS", primary_color)
            for proj in resume.projects:
                p_p = doc.add_paragraph()
                p_run = p_p.add_run(proj.name)
                p_run.font.bold = True
                p_run.font.size = Pt(10)
                if proj.technologies:
                    t_run = p_p.add_run(f" [{', '.join(proj.technologies)}]")
                    t_run.font.size = Pt(9)
                    t_run.font.color.rgb = RGBColor(100, 116, 139)

                desc_p = doc.add_paragraph(proj.description)
                desc_p.paragraph_format.space_after = Pt(4)
                desc_p.runs[0].font.size = Pt(9.5)

        # Education
        if resume.education:
            DocxRenderer._add_heading(doc, "EDUCATION", primary_color)
            for edu in resume.education:
                edu_p = doc.add_paragraph()
                deg_r = edu_p.add_run(f"{edu.degree} in {edu.field_of_study}")
                deg_r.font.bold = True
                deg_r.font.size = Pt(10)

                inst_r = edu_p.add_run(f" — {edu.institution}")
                inst_r.font.size = Pt(10)

                if edu.graduation_year:
                    yr_r = edu_p.add_run(f" ({edu.graduation_year})")
                    yr_r.font.size = Pt(9.5)
                    yr_r.font.color.rgb = RGBColor(100, 116, 139)
                edu_p.paragraph_format.space_after = Pt(4)

        # Certifications
        if resume.certifications:
            DocxRenderer._add_heading(doc, "CERTIFICATIONS", primary_color)
            for cert in resume.certifications:
                c_p = doc.add_paragraph()
                c_run = c_p.add_run(f"{cert.name} — {cert.issuer}")
                c_run.font.size = Pt(9.5)
                if cert.issue_year:
                    c_run2 = c_p.add_run(f" ({cert.issue_year})")
                    c_run2.font.size = Pt(9)
                    c_run2.font.color.rgb = RGBColor(100, 116, 139)
                c_p.paragraph_format.space_after = Pt(2)

        buffer = io.BytesIO()
        doc.save(buffer)
        return buffer.getvalue()

    @staticmethod
    def render_cover_letter(letter_data: StructuredCoverLetter | dict[str, Any], template_id: str = "modern") -> bytes:
        """Renders a structured cover letter into a styled .docx byte buffer."""
        if isinstance(letter_data, dict):
            letter = StructuredCoverLetter.model_validate(letter_data)
        else:
            letter = letter_data

        doc = docx.Document()
        for section in doc.sections:
            section.top_margin = Inches(1.0)
            section.bottom_margin = Inches(1.0)
            section.left_margin = Inches(1.0)
            section.right_margin = Inches(1.0)

        # Sender Name
        name_p = doc.add_paragraph()
        name_r = name_p.add_run(letter.sender_name)
        name_r.font.size = Pt(18)
        name_r.font.bold = True
        name_p.paragraph_format.space_after = Pt(2)

        # Sender Contact
        contact_parts = [letter.sender_email]
        if letter.sender_phone:
            contact_parts.append(letter.sender_phone)
        if letter.sender_location:
            contact_parts.append(letter.sender_location)

        contact_p = doc.add_paragraph(" | ".join(contact_parts))
        contact_p.paragraph_format.space_after = Pt(16)
        contact_p.runs[0].font.size = Pt(9.5)
        contact_p.runs[0].font.color.rgb = RGBColor(100, 116, 139)

        # Recipient Info
        rec_p = doc.add_paragraph()
        rec_r = rec_p.add_run(f"To: Hiring Team\n{letter.target_company}\nRe: Application for {letter.target_title}")
        rec_r.font.size = Pt(10)
        rec_p.paragraph_format.space_after = Pt(16)

        # Salutation
        sal_p = doc.add_paragraph(letter.salutation)
        sal_p.paragraph_format.space_after = Pt(12)
        sal_p.runs[0].font.size = Pt(10.5)

        # Opening
        open_p = doc.add_paragraph(letter.opening_paragraph)
        open_p.paragraph_format.space_after = Pt(12)
        open_p.runs[0].font.size = Pt(10)

        # Body paragraphs
        for body_p in letter.body_paragraphs:
            bp = doc.add_paragraph(body_p)
            bp.paragraph_format.space_after = Pt(12)
            bp.runs[0].font.size = Pt(10)

        # Closing
        close_p = doc.add_paragraph(letter.closing_paragraph)
        close_p.paragraph_format.space_after = Pt(12)
        close_p.runs[0].font.size = Pt(10)

        # Call to action
        cta_p = doc.add_paragraph(letter.call_to_action)
        cta_p.paragraph_format.space_after = Pt(16)
        cta_p.runs[0].font.size = Pt(10)

        # Sign-off
        sign_p = doc.add_paragraph(f"{letter.sign_off}\n\n{letter.sender_name}")
        sign_p.runs[0].font.size = Pt(10.5)

        buffer = io.BytesIO()
        doc.save(buffer)
        return buffer.getvalue()

    @staticmethod
    def _add_heading(doc: Any, text: str, color: RGBColor) -> None:
        """Adds a clean uppercase section heading."""
        p = doc.add_paragraph()
        r = p.add_run(text)
        r.font.size = Pt(11)
        r.font.bold = True
        r.font.color.rgb = color
        p.paragraph_format.space_before = Pt(8)
        p.paragraph_format.space_after = Pt(4)


docx_renderer = DocxRenderer()
