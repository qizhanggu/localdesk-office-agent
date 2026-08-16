using System;
using System.Drawing;
using System.Windows.Forms;

public static class Phase5TestApp
{
    [STAThread]
    public static void Main()
    {
        Application.EnableVisualStyles();
        var form = new Form { Text = "LocalDesk Phase 5 Test App", ClientSize = new Size(520, 260), FormBorderStyle = FormBorderStyle.FixedDialog, MaximizeBox = false };
        var heading = new Label { Text = "LocalDesk Phase 5 safe desktop test", Location = new Point(24, 22), AutoSize = true, Font = new Font("Segoe UI", 13, FontStyle.Bold) };
        var note = new Label { Text = "Input is local-only and never transmitted.", Location = new Point(24, 58), AutoSize = true };
        var input = new TextBox { Name = "task_input", AccessibleName = "Task input", Location = new Point(24, 88), Size = new Size(470, 25) };
        var submit = new Button { Name = "submit", AccessibleName = "Submit safe demo", Text = "Submit safe demo", Location = new Point(185, 130), Size = new Size(150, 30) };
        var fallback = new Button { Name = "fallback", AccessibleName = "Run fallback demo", Text = "Run fallback demo", Location = new Point(185, 166), Size = new Size(150, 30) };
        var status = new Label { Name = "status", Text = "Status: awaiting safe demo input", Location = new Point(24, 216), AutoSize = true };
        submit.Click += (sender, args) => status.Text = "Status: submitted " + input.Text;
        fallback.Click += (sender, args) => status.Text = "Status: fallback demo completed";
        form.AcceptButton = submit;
        form.Controls.AddRange(new Control[] { heading, note, input, submit, fallback, status });
        Application.Run(form);
    }
}
