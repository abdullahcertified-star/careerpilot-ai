"""PDF document renderer for resumes and cover letters using ReportLab.

Produces text-selectable, beautifully styled PDF documents with proper typographic
hierarchy and standard margins.
"""

import io
from typing import Any
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer
from app.services.documents.schemas import StructuredCoverLetter, StructuredResume


class PdfRenderer:
    """Renders structured resume and cover letter data into downloadable text-selectable PDF files."""

    @staticmethod
    def render_resume(resume_data: StructuredResume | dict[str, Any], template_id: str = "modern") -> bytes:
        """Renders a structured resume into a text-selectable PDF byte buffer."""
        if isinstance(resume_data, dict):
            resume = StructuredResume.model_validate(resume_data)
        else:
            resume = resume_data

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            leftMargin=40,
            rightMargin=40,
            topMargin=40,
            bottomMargin=40,
            title=f"{resume.full_name} - Resume",
            author="CareerPilot AI",
        )

        styles = getSampleStyleSheet()

        # Custom Palette
        primary_hex = "#1e3a8a" if template_id == "modern" else ("#0f172a" if template_id == "technical" else "#111827")
        primary_color = colors.HexColor(primary_hex)
        secondary_color = colors.HexColor("#475569")

        # Custom Typographic Styles
        name_style = ParagraphStyle(
            "CandidateName",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=20,
            leading=24,
            textColor=primary_color,
            spaceAfter=2,
        )

        contact_style = ParagraphStyle(
            "ContactInfo",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=8.5,
            leading=12,
            textColor=secondary_color,
            spaceAfter=6,
        )

        target_style = ParagraphStyle(
            "TargetHeader",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=9.5,
            leading=13,
            textColor=primary_color,
            spaceAfter=8,
        )

        section_heading_style = ParagraphStyle(
            "SectionHeading",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=10.5,
            leading=14,
            textColor=primary_color,
            spaceBefore=8,
            spaceAfter=3,
        )

        body_style = ParagraphStyle(
            "BodyDark",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=9,
            leading=12.5,
            textColor=colors.HexColor("#1e293b"),
            spaceAfter=4,
        )

        bullet_style = ParagraphStyle(
            "BulletItem",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=8.5,
            leading=11.5,
            textColor=colors.HexColor("#334155"),
            leftIndent=12,
            spaceAfter=2,
        )

        story = []

        # Name & Contact Info
        story.append(Paragraph(resume.full_name, name_style))

        contact_parts = [resume.email]
        if resume.phone:
            contact_parts.append(resume.phone)
        if resume.location:
            contact_parts.append(resume.location)
        if resume.linkedin_url:
            contact_parts.append(resume.linkedin_url)
        story.append(Paragraph(" | ".join(contact_parts), contact_style))

        # Target Role
        story.append(
            Paragraph(
                f"<b>TARGET ROLE:</b> {resume.target_title} • <b>{resume.target_company}</b>",
                target_style,
            )
        )
        story.append(HRFlowable(width="100%", thickness=1, color=primary_color, spaceBefore=2, spaceAfter=6))

        # Professional Summary
        if resume.professional_summary:
            story.append(Paragraph("PROFESSIONAL SUMMARY", section_heading_style))
            story.append(Paragraph(resume.professional_summary, body_style))

        # Core Skills
        if resume.highlighted_skills:
            story.append(Paragraph("CORE SKILLS & TECHNOLOGIES", section_heading_style))
            skills_text = " • ".join(resume.highlighted_skills)
            story.append(Paragraph(skills_text, body_style))

        # Experience
        if resume.experience:
            story.append(Paragraph("PROFESSIONAL EXPERIENCE", section_heading_style))
            for exp in resume.experience:
                date_str = f"{exp.start_date} – {exp.end_date}"
                exp_header = f"<b>{exp.title}</b> — <font color='{primary_hex}'>{exp.company}</font> <font color='#64748b' size='8'>({date_str})</font>"
                story.append(Paragraph(exp_header, body_style))
                for bullet in exp.bullets:
                    story.append(Paragraph(f"• {bullet}", bullet_style))
                story.append(Spacer(1, 3))

        # Projects
        if resume.projects:
            story.append(Paragraph("KEY PROJECTS", section_heading_style))
            for proj in resume.projects:
                tech_str = f" <font color='#64748b' size='8'>[{', '.join(proj.technologies)}]</font>" if proj.technologies else ""
                story.append(Paragraph(f"<b>{proj.name}</b>{tech_str}", body_style))
                story.append(Paragraph(proj.description, bullet_style))

        # Education
        if resume.education:
            story.append(Paragraph("EDUCATION", section_heading_style))
            for edu in resume.education:
                yr_str = f" ({edu.graduation_year})" if edu.graduation_year else ""
                edu_text = f"<b>{edu.degree} in {edu.field_of_study}</b> — {edu.institution}{yr_str}"
                story.append(Paragraph(edu_text, body_style))

        # Certifications
        if resume.certifications:
            story.append(Paragraph("CERTIFICATIONS", section_heading_style))
            for cert in resume.certifications:
                yr_str = f" ({cert.issue_year})" if cert.issue_year else ""
                cert_text = f"<b>{cert.name}</b> — {cert.issuer}{yr_str}"
                story.append(Paragraph(cert_text, body_style))

        doc.build(story)
        return buffer.getvalue()

    @staticmethod
    def render_cover_letter(letter_data: StructuredCoverLetter | dict[str, Any], template_id: str = "modern") -> bytes:
        """Renders a structured cover letter into a text-selectable PDF byte buffer."""
        if isinstance(letter_data, dict):
            letter_obj = StructuredCoverLetter.model_validate(letter_data)
        else:
            letter_obj = letter_data

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            leftMargin=50,
            rightMargin=50,
            topMargin=50,
            bottomMargin=50,
            title=f"{letter_obj.sender_name} - Cover Letter",
            author="CareerPilot AI",
        )

        styles = getSampleStyleSheet()

        primary_hex = "#1e3a8a" if template_id == "modern" else "#0f172a"
        primary_color = colors.HexColor(primary_hex)

        name_style = ParagraphStyle(
            "SenderName",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=16,
            leading=20,
            textColor=primary_color,
            spaceAfter=2,
        )

        contact_style = ParagraphStyle(
            "SenderContact",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#64748b"),
            spaceAfter=14,
        )

        recipient_style = ParagraphStyle(
            "RecipientInfo",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=9.5,
            leading=14,
            textColor=colors.HexColor("#1e293b"),
            spaceAfter=14,
        )

        salutation_style = ParagraphStyle(
            "Salutation",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=10,
            leading=14,
            textColor=colors.HexColor("#0f172a"),
            spaceAfter=10,
        )

        body_style = ParagraphStyle(
            "LetterBody",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=9.5,
            leading=15,
            textColor=colors.HexColor("#334155"),
            spaceAfter=12,
        )

        story = []

        # Header
        story.append(Paragraph(letter_obj.sender_name, name_style))
        contact = [letter_obj.sender_email]
        if letter_obj.sender_phone:
            contact.append(letter_obj.sender_phone)
        if letter_obj.sender_location:
            contact.append(letter_obj.sender_location)
        story.append(Paragraph(" | ".join(contact), contact_style))

        story.append(HRFlowable(width="100%", thickness=1, color=primary_color, spaceBefore=0, spaceAfter=14))

        # Recipient Info
        rec_text = f"<b>To:</b> Hiring Team<br/><b>Company:</b> {letter_obj.target_company}<br/><b>Role:</b> {letter_obj.target_title}"
        story.append(Paragraph(rec_text, recipient_style))

        # Salutation
        story.append(Paragraph(letter_obj.salutation, salutation_style))

        # Opening
        story.append(Paragraph(letter_obj.opening_paragraph, body_style))

        # Body paragraphs
        for p in letter_obj.body_paragraphs:
            story.append(Paragraph(p, body_style))

        # Closing
        story.append(Paragraph(letter_obj.closing_paragraph, body_style))

        # Call to Action
        story.append(Paragraph(letter_obj.call_to_action, body_style))

        # Sign-off
        story.append(Spacer(1, 8))
        story.append(Paragraph(f"{letter_obj.sign_off}<br/><br/><b>{letter_obj.sender_name}</b>", body_style))

        doc.build(story)
        return buffer.getvalue()


pdf_renderer = PdfRenderer()
